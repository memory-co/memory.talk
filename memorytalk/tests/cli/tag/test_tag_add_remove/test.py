"""`memory-talk tag {add,remove} <sess_id> <tags...>` — happy path + idempotency."""
from __future__ import annotations
import json

from memory_talk_v2.schemas import ContentBlock, IngestRound, IngestSessionRequest


async def _seed_session(cli_env):
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="platform-a", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="hi")],
            is_sidechain=False,
        )],
    ))
    return "sess_platform-a"


async def _run_add(cli_env, sid: str, *tags: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "add", sid, *tags,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def _run_remove(cli_env, sid: str, *tags: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "remove", sid, *tags,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def _session_events(cli_env, sid: str) -> list[dict]:
    db = cli_env.app.state.db
    s = await db.sessions.get(sid)
    return await db.sessions.read_events(s["source"], sid)


async def test_add_single_tag(cli_env):
    sid = await _seed_session(cli_env)
    exit_code, out = await _run_add(cli_env, sid, "decision")
    assert exit_code == 0
    assert out["status"] == "ok"
    assert out["tags"] == ["decision"]


async def test_add_multiple_tags_in_one_call(cli_env):
    sid = await _seed_session(cli_env)
    exit_code, out = await _run_add(cli_env, sid, "decision", "project:mt", "v2")
    assert exit_code == 0
    assert out["tags"] == ["decision", "project:mt", "v2"]
    # Each real addition emits one event
    kinds = [e["kind"] for e in await _session_events(cli_env, sid) if e["kind"] == "tag_added"]
    assert kinds == ["tag_added", "tag_added", "tag_added"]


async def test_add_existing_tag_is_idempotent(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision")
    # Re-add the same tag — no-op on state, no new event
    exit_code, out = await _run_add(cli_env, sid, "decision")
    assert exit_code == 0
    assert out["tags"] == ["decision"]
    kinds = [e["kind"] for e in await _session_events(cli_env, sid) if e["kind"] == "tag_added"]
    assert kinds == ["tag_added"]  # only the first add emitted


async def test_add_mixed_new_and_existing(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision")
    exit_code, out = await _run_add(cli_env, sid, "decision", "important")
    assert exit_code == 0
    assert out["tags"] == ["decision", "important"]
    # Only "important" was actually new the second call — 1 new event
    kinds = [e["kind"] for e in await _session_events(cli_env, sid) if e["kind"] == "tag_added"]
    assert kinds == ["tag_added", "tag_added"]  # one from first call, one from second


async def test_remove_tag(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision", "important")
    exit_code, out = await _run_remove(cli_env, sid, "decision")
    assert exit_code == 0
    assert out["tags"] == ["important"]
    kinds = [e["kind"] for e in await _session_events(cli_env, sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added", "tag_removed"]


async def test_remove_nonexistent_tag_is_idempotent(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision")
    exit_code, out = await _run_remove(cli_env, sid, "never-was-here")
    assert exit_code == 0
    assert out["tags"] == ["decision"]  # unchanged
    kinds = [e["kind"] for e in await _session_events(cli_env, sid) if e["kind"] == "tag_removed"]
    assert kinds == []  # no event for a no-op removal


async def test_full_lifecycle(cli_env):
    sid = await _seed_session(cli_env)
    _, o1 = await _run_add(cli_env, sid, "a", "b")
    assert o1["tags"] == ["a", "b"]
    _, o2 = await _run_add(cli_env, sid, "b", "c")  # b existing, c new
    assert o2["tags"] == ["a", "b", "c"]
    _, o3 = await _run_remove(cli_env, sid, "a", "missing")  # a real, missing no-op
    assert o3["tags"] == ["b", "c"]
    _, o4 = await _run_remove(cli_env, sid, "b", "c")
    assert o4["tags"] == []
    kinds = [e["kind"] for e in await _session_events(cli_env, sid) if e["kind"].startswith("tag_")]
    # Events are only emitted for real state changes: a,b,c added; a,b,c removed
    assert kinds == ["tag_added"] * 3 + ["tag_removed"] * 3
