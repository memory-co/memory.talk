"""adapters/claude_code -- rounds from ~/.claude/projects. See README.md."""
import json
import os
import time

import pytest

from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def agent(client, home, monkeypatch):
    bindir = home / "bin"; bindir.mkdir()
    fake = bindir / "claude"; fake.write_text("#!/bin/sh\nsleep 60\n"); fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    w = client.post("/api/works", json={"goal": "让 agent 干活"}).json()
    proj = home / "ws" / "proj"; proj.mkdir(parents=True)
    s = client.post(f"/api/works/{w['id']}/sessions", json={"uri": f"claude://{proj}"}).json()
    time.sleep(0.05)
    d = home / "claude" / str(proj).replace("/", "-"); d.mkdir(parents=True)
    return w, s, proj, d / "sess.jsonl"


ROWS = [
    {"type": "user", "uuid": "u1", "timestamp": "2026-09-05T10:00:00Z", "message": {"content": [{"type": "text", "text": "把配置改成环境变量"}]}},
    {"type": "assistant", "uuid": "a1", "message": {"content": [{"type": "text", "text": "好"}, {"type": "tool_use", "name": "Edit", "input": {"f": "config.py"}}]}},
    {"type": "user", "uuid": "u2", "toolUseResult": {}, "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
    {"type": "user", "uuid": "u3", "isMeta": True, "message": {"content": "caveat"}},
    {"type": "user", "uuid": "u4", "isSidechain": True, "message": {"content": "旁支"}},
]


def _write(path, rows, mode="w"):
    with open(path, mode) as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))


def test_agent_session_has_rounds_capability(agent):
    _, s, _, _ = agent
    assert s["scheme"] == "claude" and "rounds" in s["handle"]["capabilities"]


def test_no_transcript_yet_means_no_rounds(client, agent):
    w, s, _, _ = agent
    assert client.get(f"/api/works/{w['id']}/sessions/{s['id']}/rounds").json() == []


def test_roles_are_classified_and_sidechain_skipped(client, agent):
    w, s, _, path = agent
    _write(path, ROWS)
    rounds = client.get(f"/api/works/{w['id']}/sessions/{s['id']}/rounds").json()
    assert [(r["id"], r["role"]) for r in rounds] == [("u1", "human"), ("a1", "assistant"), ("u2", "tool"), ("u3", "system")]
    assert "[Edit]" in rounds[1]["text"]


def test_rounds_are_deduplicated_and_appended(client, agent, svc):
    w, s, _, path = agent
    _write(path, ROWS)
    client.get(f"/api/works/{w['id']}/sessions/{s['id']}/rounds")
    assert len(client.get(f"/api/works/{w['id']}/sessions/{s['id']}/rounds").json()) == 4       # 再读不重复
    _write(path, [{"type": "assistant", "uuid": "a2", "message": {"content": [{"type": "text", "text": "改完了"}]}}], "a")
    assert client.get(f"/api/works/{w['id']}/sessions/{s['id']}/rounds").json()[-1]["id"] == "a2"
    assert len(svc.works.repo.read(w["id"], "rounds", sub=s["id"])) == 5                         # append-only 的流
