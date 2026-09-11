"""adapters/codex -- rollout parsing. See README.md."""
import json
from pathlib import Path

from memorytalk.backend.services.work_servers.adapters import CodexAdapter

ROWS = [
    {"type": "session_meta", "payload": {"cwd": "/w/p"}},
    {"type": "event_msg", "timestamp": "t1", "payload": {"type": "user_message", "message": "hi"}},
    {"type": "event_msg", "timestamp": "t2", "payload": {"type": "task_started"}},
    {"type": "response_item", "timestamp": "t3", "payload": {"type": "function_call", "name": "shell", "arguments": "ls"}},
    {"type": "response_item", "timestamp": "t4", "payload": {"type": "function_call_output", "output": "a b"}},
    {"type": "event_msg", "timestamp": "t5", "payload": {"type": "agent_message", "message": "done"}},
]


def _rollout(home):
    root = home / "codex" / "2026" / "09" / "05"; root.mkdir(parents=True)
    p = root / "rollout-2026-09-05T10-00-00-abc.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    return p


def test_find_matches_by_cwd(home):
    p = _rollout(home)
    ad = CodexAdapter(home / "codex")
    assert ad.find(Path("/w/p"), 0) == p
    assert ad.find(Path("/other"), 0) is None


def test_rounds_keep_conversation_and_tools_skip_control_events(home):
    p = _rollout(home)
    assert [(r.role, r.text) for r in CodexAdapter(home / "codex").rounds(p)] == [
        ("human", "hi"), ("assistant", "[shell] ls"), ("tool", "[result] a b"), ("assistant", "done")]
