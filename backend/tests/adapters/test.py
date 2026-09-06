"""agent server 的把手:从平台会话记录读 round → 追加进 task 的 rounds.jsonl(append-only)。"""
import json
import os
import shutil
import time

import pytest

needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="需要 tmux")


def _claude_transcript(root, cwd, rows):
    d = root / str(cwd).replace("/", "-")
    d.mkdir(parents=True)
    p = d / "sess.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


@needs_tmux
def test_claude_member_rounds(client, home, monkeypatch):
    # 让 "claude" 这个协议在 PATH 里有个命令可跑(假的,只要 tmux 能起)
    bindir = home / "bin"; bindir.mkdir()
    fake = bindir / "claude"; fake.write_text("#!/bin/sh\nsleep 60\n"); fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")

    t = client.post("/api/tasks", json={"goal": "让 agent 干活"}).json()
    proj = home / "ws" / "proj"; proj.mkdir(parents=True)
    m = client.post(f"/api/tasks/{t['id']}/members", json={"uri": f"claude://{proj}"}).json()
    assert m["scheme"] == "claude" and "rounds" in m["handle"]["capabilities"]
    assert client.get(f"/api/tasks/{t['id']}/members/{m['id']}/rounds").json() == []

    # 会话记录出现了(成员创建之后)
    time.sleep(0.05)
    rows = [
        {"type": "user", "uuid": "u1", "timestamp": "2026-09-05T10:00:00Z", "cwd": str(proj),
         "message": {"content": [{"type": "text", "text": "把配置改成环境变量"}]}},
        {"type": "assistant", "uuid": "a1", "timestamp": "2026-09-05T10:00:05Z",
         "message": {"content": [{"type": "text", "text": "好"}, {"type": "tool_use", "name": "Edit", "input": {"f": "config.py"}}]}},
        {"type": "user", "uuid": "u2", "toolUseResult": {}, "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "user", "uuid": "u3", "isMeta": True, "message": {"content": "caveat"}},
        {"type": "user", "uuid": "u4", "isSidechain": True, "message": {"content": "旁支"}},
    ]
    _claude_transcript(home / "claude", proj, rows)

    rounds = client.get(f"/api/tasks/{t['id']}/members/{m['id']}/rounds").json()
    assert [(r["id"], r["role"]) for r in rounds] == [("u1", "human"), ("a1", "assistant"), ("u2", "tool"), ("u3", "system")]
    assert "[Edit]" in rounds[1]["text"]

    # append-only:再读不重复;新 round 追加
    assert len(client.get(f"/api/tasks/{t['id']}/members/{m['id']}/rounds").json()) == 4
    p = home / "claude" / str(proj).replace("/", "-") / "sess.jsonl"
    with open(p, "a") as f:
        f.write(json.dumps({"type": "assistant", "uuid": "a2", "message": {"content": [{"type": "text", "text": "改完了"}]}}) + "\n")
    assert [r["id"] for r in client.get(f"/api/tasks/{t['id']}/members/{m['id']}/rounds").json()][-1] == "a2"
    jsonl = home / "home" / "tasks" / t["id"] / "sessions" / m["id"] / "rounds.jsonl"
    assert len(jsonl.read_text().splitlines()) == 5


def test_codex_adapter_parses(home):
    from pathlib import Path
    from services.servers.adapters import CodexAdapter
    root = home / "codex" / "2026" / "09" / "05"; root.mkdir(parents=True)
    p = root / "rollout-2026-09-05T10-00-00-abc.jsonl"
    rows = [
        {"type": "session_meta", "payload": {"cwd": "/w/p"}},
        {"type": "event_msg", "timestamp": "t1", "payload": {"type": "user_message", "message": "hi"}},
        {"type": "event_msg", "timestamp": "t2", "payload": {"type": "task_started"}},
        {"type": "response_item", "timestamp": "t3", "payload": {"type": "function_call", "name": "shell", "arguments": "ls"}},
        {"type": "response_item", "timestamp": "t4", "payload": {"type": "function_call_output", "output": "a b"}},
        {"type": "event_msg", "timestamp": "t5", "payload": {"type": "agent_message", "message": "done"}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ad = CodexAdapter(home / "codex")
    assert ad.find(Path("/w/p"), 0) == p and ad.find(Path("/other"), 0) is None
    assert [(r.role, r.text) for r in ad.rounds(p)] == [
        ("human", "hi"), ("assistant", "[shell] ls"), ("tool", "[result] a b"), ("assistant", "done")]


def test_kimi_adapter_parses(home):
    from pathlib import Path
    from services.servers.adapters import KimiAdapter
    sd = home / "kimi" / "wd_u_abc" / "session_1"; (sd / "agents" / "main").mkdir(parents=True)
    (sd / "state.json").write_text(json.dumps({"workDir": "/w/p", "createdAt": "2026-09-06T00:00:00Z"}))
    wire = sd / "agents" / "main" / "wire.jsonl"
    rows = [
        {"type": "metadata", "protocol_version": "1.5"},
        {"type": "turn.prompt", "time": 1, "input": [{"type": "text", "text": "拉个镜像"}]},
        {"type": "context.append_loop_event", "time": 2, "event": {"type": "content.part", "uuid": "c1", "part": {"type": "think", "think": "先查 docker"}}},
        {"type": "context.append_loop_event", "time": 3, "event": {"type": "tool.call", "uuid": "t1", "name": "Bash", "args": {"command": "docker images"}}},
        {"type": "context.append_loop_event", "time": 4, "event": {"type": "tool.result", "toolCallId": "tc1", "result": {"output": "REPOSITORY TAG"}}},
        {"type": "context.append_loop_event", "time": 5, "event": {"type": "content.part", "uuid": "c2", "part": {"type": "text", "text": "拉好了"}}},
        {"type": "turn.ended", "time": 6},
    ]
    wire.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ad = KimiAdapter(home / "kimi")
    assert ad.find(Path("/w/p"), 0) == wire and ad.find(Path("/other"), 0) is None
    assert [(r.role, r.text) for r in ad.rounds(wire)] == [
        ("human", "拉个镜像"), ("assistant", "[thinking] 先查 docker"), ("assistant", '[Bash] {"command": "docker images"}'),
        ("tool", "[result] REPOSITORY TAG"), ("assistant", "拉好了")]
