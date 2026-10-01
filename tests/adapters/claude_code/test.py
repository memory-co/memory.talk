"""adapters/claude_code -- rounds from ~/.claude/projects, sliced into agent.turn spans. See README.md."""
import hashlib
import json
import os
import time

import pytest

from tests._util import trace
from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def agent(client, home, monkeypatch):
    bindir = home / "bin"; bindir.mkdir()
    fake = bindir / "claude"; fake.write_text("#!/bin/sh\nsleep 60\n"); fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    w = client.post("/api/works", json={"goal": "让 agent 干活"}).json()
    proj = home / "ws" / "proj"; proj.mkdir(parents=True)
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"claude://{proj}"}).json()
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
    assert client.get(f"/api/works/{w['id']}/worklets/{s['id']}/rounds").json() == []


def test_roles_are_classified_and_sidechain_skipped(client, agent):
    w, s, _, path = agent
    _write(path, ROWS)
    rounds = client.get(f"/api/works/{w['id']}/worklets/{s['id']}/rounds").json()
    assert [(r["id"], r["role"]) for r in rounds] == [("u1", "human"), ("a1", "assistant"), ("u2", "tool"), ("u3", "system")]
    assert "[Edit]" in rounds[1]["text"]


def test_rounds_are_deduplicated_and_appended(client, agent, svc):
    w, s, _, path = agent
    _write(path, ROWS)
    client.get(f"/api/works/{w['id']}/worklets/{s['id']}/rounds")
    assert len(client.get(f"/api/works/{w['id']}/worklets/{s['id']}/rounds").json()) == 4       # 再读不重复
    _write(path, [{"type": "assistant", "uuid": "a2", "message": {"content": [{"type": "text", "text": "改完了"}]}}], "a")
    assert client.get(f"/api/works/{w['id']}/worklets/{s['id']}/rounds").json()[-1]["id"] == "a2"
    assert len(svc.works.trace_repo.read_rounds(s["id"])) == 5                                   # worktrace.db 的 rounds 表,只追加


# ---- agent 轮次:同步 round 时切出来,写成 worklet 段下的 agent.turn 段 ----

S = 1_000_000_000
T0 = 1788602400                     # 2026-09-05T10:00:00Z


def _msg(uuid, ts, text, kind="user"):
    return {"type": kind, "uuid": uuid, "timestamp": ts, "message": {"content": [{"type": "text", "text": text}]}}


TURNS = [
    {"type": "user", "uuid": "s0", "isMeta": True, "timestamp": "2026-09-05T09:59:00Z", "message": {"content": "caveat"}},
    _msg("h1", "2026-09-05T10:00:00Z", "第一件事"),
    _msg("a1", "2026-09-05T10:00:30.5Z", "好", "assistant"),
    _msg("h2", "2026-09-05T10:01:00Z", "第二件事"),
]


def _turns(client, w):
    return [s for s in trace(client, w["id"])[0] if s["name"] == "agent.turn"]


def _rounds(client, w, s):
    return client.get(f"/api/works/{w['id']}/worklets/{s['id']}/rounds").json()


def test_rounds_are_sliced_into_turns_under_the_worklet_span(client, agent):
    w, s, _, path = agent
    _write(path, TURNS)
    _rounds(client, w, s)
    [seg] = [x for x in trace(client, w["id"])[0] if x["name"] == "worklet"]
    first, second = _turns(client, w)
    assert first["spanId"] == hashlib.sha256(f"memorytalk/span/turn/{s['id']}/h1".encode()).hexdigest()[:16]
    assert first["parentSpanId"] == second["parentSpanId"] == seg["spanId"] and first["traceId"] == seg["traceId"]
    assert (first["start"], first["end"], first["status"]) == (T0 * S, T0 * S + 30_500_000_000, 1)
    assert (first["memorytalk.round.first"], first["memorytalk.round.last"], first["memorytalk.round.count"]) == ("h1", "a1", 2)
    assert first["gen_ai.system"] == "anthropic" and first["memorytalk.worklet.id"] == s["id"] and "user.id" not in first
    assert (second["start"], second["end"], second["memorytalk.open"]) == ((T0 + 60) * S, None, True)


def test_resyncing_updates_the_open_turn_in_place(client, agent):
    w, s, _, path = agent
    _write(path, TURNS)
    _rounds(client, w, s)
    _rounds(client, w, s)                                                                   # 没有新 round:不动
    _write(path, [_msg("a2", "2026-09-05T10:02:00Z", "做完了", "assistant")], "a")
    _rounds(client, w, s)
    first, second = _turns(client, w)                                                      # 还是两段,按第一条 round 认
    assert (second["memorytalk.round.last"], second["memorytalk.round.count"], second["end"]) == ("a2", 2, None)
    _write(path, [_msg("h3", "2026-09-05T10:03:00Z", "第三件事")], "a")
    _rounds(client, w, s)
    turns = _turns(client, w)
    assert len(turns) == 3 and turns[1]["end"] == (T0 + 120) * S and turns[1]["status"] == 1


def test_detach_syncs_once_more_and_closes_the_open_turn(client, agent, H):
    w, s, _, path = agent
    _write(path, TURNS)
    _rounds(client, w, s)
    _write(path, [_msg("a2", "2026-09-05T10:02:00Z", "做完了", "assistant")], "a")          # 关之前写进来、还没人读过
    client.delete(f"/api/works/{w['id']}/worklets/{s['id']}", headers=H("bob"))
    _, second = _turns(client, w)
    assert (second["end"], second["status"], second["memorytalk.round.count"]) == ((T0 + 120) * S, 1, 2)
    assert "memorytalk.open" not in second and "memorytalk.end.user.id" not in second      # 轮次不记人


def test_archive_closes_the_open_turn(client, agent):
    w, s, _, path = agent
    _write(path, TURNS)
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})                     # 归档前也最后收一次 round
    _, second = _turns(client, w)
    assert second["end"] == (T0 + 60) * S and second["status"] == 1


def test_a_vanished_site_closes_the_open_turn_as_unset(client, agent, svc):
    w, s, _, path = agent
    _write(path, TURNS)
    _rounds(client, w, s)
    svc.work_servers.destroy("claude", s["id"])                                            # agent 自己退出了
    client.get(f"/api/works/{w['id']}/worklets")
    first, second = _turns(client, w)
    assert (first["status"], second["status"], second["end"]) == (1, 0, (T0 + 60) * S)    # 跟 worklet 段一样是 Unset


def test_detach_after_archive_does_not_sync_again(client, agent, svc):
    w, s, _, path = agent
    _write(path, TURNS)
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})                     # 归档时收了最后一次
    frozen = [r["round_id"] for r in svc.works.trace_repo.read_rounds(s["id"])]
    time.sleep(0.05)
    _write(path.with_name("other.jsonl"), [_msg("x1", "2026-09-05T11:00:00Z", "别的会话")])   # 同一个目录里后来的另一个会话
    assert client.delete(f"/api/works/{w['id']}/worklets/{s['id']}").status_code == 200
    assert [r["round_id"] for r in svc.works.trace_repo.read_rounds(s["id"])] == frozen == ["s0", "h1", "a1", "h2"]
    assert [t["memorytalk.round.first"] for t in _turns(client, w)] == ["h1", "h2"]
