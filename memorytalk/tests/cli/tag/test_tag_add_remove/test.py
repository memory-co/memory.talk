"""`memory-talk tag {add,remove} <subject_id> <tag/key>...` — happy path + idempotency.

Tags are kv-shaped now. The CLI input syntax is ``key`` or ``key:value``;
the API stores `(key, value)` rows. The remove path takes keys only.
"""
from __future__ import annotations
import json

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)


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
    # ingest() auto-stamps `sync_session: new`; strip it so these tests
    # only see the tag ops they explicitly perform.
    await cli_env.app.state.tags.remove_tags("sess_platform-a", ["sync_session"])
    return "sess_platform-a"


async def _seed_card(cli_env):
    sid = await _seed_session(cli_env)
    r = await cli_env.app.state.cards.create(CreateCardRequest(
        summary="card for tag tests",
        rounds=[CardRoundsItem(session_id=sid, indexes="1")],
    ))
    return r.card_id


async def _run_add(cli_env, sid: str, *tags: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "add", sid, *tags,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def _run_remove(cli_env, sid: str, *keys: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "remove", sid, *keys,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def _events(cli_env, subject_id: str) -> list[dict]:
    db = cli_env.app.state.db
    if subject_id.startswith("sess_"):
        s = await db.sessions.get(subject_id)
        return await db.sessions.read_events(s["source"], subject_id)
    return await db.cards.read_events(subject_id)


def _kv(out) -> list[tuple[str, str]]:
    return [(t["key"], t["value"]) for t in out["tags"]]


def _tag_kinds(events: list[dict]) -> list[str]:
    """tag_* events excluding sync_session (auto-stamped + seed cleanup noise)."""
    return [
        e["kind"] for e in events
        if e["kind"].startswith("tag_")
        and e.get("detail", {}).get("key") != "sync_session"
    ]


# -------- session: add --------

async def test_add_single_tag(cli_env):
    sid = await _seed_session(cli_env)
    exit_code, out = await _run_add(cli_env, sid, "decision")
    assert exit_code == 0
    assert out["status"] == "ok"
    assert _kv(out) == [("decision", "")]


async def test_add_multiple_tags_in_one_call(cli_env):
    sid = await _seed_session(cli_env)
    exit_code, out = await _run_add(cli_env, sid, "decision", "project:mt", "v2")
    assert exit_code == 0
    assert _kv(out) == [("decision", ""), ("project", "mt"), ("v2", "")]
    kinds = _tag_kinds(await _events(cli_env, sid))
    assert kinds == ["tag_added", "tag_added", "tag_added"]


async def test_add_existing_tag_same_value_is_idempotent(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision")
    exit_code, out = await _run_add(cli_env, sid, "decision")
    assert exit_code == 0
    assert _kv(out) == [("decision", "")]
    kinds = _tag_kinds(await _events(cli_env, sid))
    assert kinds == ["tag_added"]


async def test_add_existing_tag_different_value_is_updated(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "project:foo")
    exit_code, out = await _run_add(cli_env, sid, "project:bar")
    assert exit_code == 0
    assert _kv(out) == [("project", "bar")]
    kinds = _tag_kinds(await _events(cli_env, sid))
    assert kinds == ["tag_added", "tag_updated"]


async def test_add_mixed_new_and_existing(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision")
    exit_code, out = await _run_add(cli_env, sid, "decision", "important")
    assert exit_code == 0
    assert _kv(out) == [("decision", ""), ("important", "")]
    kinds = [k for k in _tag_kinds(await _events(cli_env, sid)) if k == "tag_added"]
    assert kinds == ["tag_added", "tag_added"]


# -------- session: remove --------

async def test_remove_tag(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision", "important")
    exit_code, out = await _run_remove(cli_env, sid, "decision")
    assert exit_code == 0
    assert _kv(out) == [("important", "")]
    kinds = _tag_kinds(await _events(cli_env, sid))
    assert kinds == ["tag_added", "tag_added", "tag_removed"]


async def test_remove_nonexistent_tag_is_idempotent(cli_env):
    sid = await _seed_session(cli_env)
    await _run_add(cli_env, sid, "decision")
    exit_code, out = await _run_remove(cli_env, sid, "never-was-here")
    assert exit_code == 0
    assert _kv(out) == [("decision", "")]
    kinds = [k for k in _tag_kinds(await _events(cli_env, sid)) if k == "tag_removed"]
    assert kinds == []


async def test_full_lifecycle(cli_env):
    sid = await _seed_session(cli_env)
    _, o1 = await _run_add(cli_env, sid, "a", "b")
    assert _kv(o1) == [("a", ""), ("b", "")]
    _, o2 = await _run_add(cli_env, sid, "b", "c")
    assert _kv(o2) == [("a", ""), ("b", ""), ("c", "")]
    _, o3 = await _run_remove(cli_env, sid, "a", "missing")
    assert _kv(o3) == [("b", ""), ("c", "")]
    _, o4 = await _run_remove(cli_env, sid, "b", "c")
    assert _kv(o4) == []
    kinds = _tag_kinds(await _events(cli_env, sid))
    assert kinds == ["tag_added"] * 3 + ["tag_removed"] * 3


# -------- card mirror --------

async def test_add_to_card(cli_env):
    cid = await _seed_card(cli_env)
    exit_code, out = await _run_add(cli_env, cid, "topic:lancedb", "status:reviewed")
    assert exit_code == 0
    assert _kv(out) == [("topic", "lancedb"), ("status", "reviewed")]
    kinds = _tag_kinds(await _events(cli_env, cid))
    assert kinds == ["tag_added", "tag_added"]


async def test_remove_from_card(cli_env):
    cid = await _seed_card(cli_env)
    await _run_add(cli_env, cid, "topic:lancedb", "status:reviewed")
    exit_code, out = await _run_remove(cli_env, cid, "topic")
    assert exit_code == 0
    assert _kv(out) == [("status", "reviewed")]
