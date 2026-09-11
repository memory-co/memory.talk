"""adapters/kimi -- wire.jsonl parsing. See README.md."""
import json
from pathlib import Path

from memorytalk.backend.services.work_servers.adapters import KimiAdapter

ROWS = [
    {"type": "metadata", "protocol_version": "1.5"},
    {"type": "turn.prompt", "time": 1, "input": [{"type": "text", "text": "拉个镜像"}]},
    {"type": "context.append_loop_event", "time": 2, "event": {"type": "content.part", "uuid": "c1", "part": {"type": "think", "think": "先查 docker"}}},
    {"type": "context.append_loop_event", "time": 3, "event": {"type": "tool.call", "uuid": "t1", "name": "Bash", "args": {"command": "docker images"}}},
    {"type": "context.append_loop_event", "time": 4, "event": {"type": "tool.result", "toolCallId": "tc1", "result": {"output": "REPOSITORY TAG"}}},
    {"type": "context.append_loop_event", "time": 5, "event": {"type": "content.part", "uuid": "c2", "part": {"type": "text", "text": "拉好了"}}},
    {"type": "turn.ended", "time": 6},
]


def _wire(home):
    sd = home / "kimi" / "wd_u_abc" / "session_1"; (sd / "agents" / "main").mkdir(parents=True)
    (sd / "state.json").write_text(json.dumps({"workDir": "/w/p", "createdAt": "2026-09-06T00:00:00Z"}))
    wire = sd / "agents" / "main" / "wire.jsonl"
    wire.write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    return wire


def test_find_matches_by_workdir(home):
    wire = _wire(home)
    ad = KimiAdapter(home / "kimi")
    assert ad.find(Path("/w/p"), 0) == wire and ad.find(Path("/other"), 0) is None


def test_rounds_from_prompt_parts_and_tools(home):
    wire = _wire(home)
    assert [(r.role, r.text) for r in KimiAdapter(home / "kimi").rounds(wire)] == [
        ("human", "拉个镜像"), ("assistant", "[thinking] 先查 docker"), ("assistant", '[Bash] {"command": "docker images"}'),
        ("tool", "[result] REPOSITORY TAG"), ("assistant", "拉好了")]
