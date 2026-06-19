"""PATCH /v4/sessions/{sid}/tags — kv tag set / unset / query.

Covers PATCH semantics (unrelated keys preserved), all the validation
constraints (key regex, value length, total count, set ∩ unset), the
empty-body query path, and 404 for missing sids.
"""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session
from memorytalk.util.tags import MAX_TAGS_PER_OBJECT, MAX_VALUE_LEN


pytestmark = pytest.mark.asyncio


async def _seed(client, sid: str = "t-1") -> str:
    r = await ingest_session(client, sid, rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hi"}]},
    ])
    r.raise_for_status()
    return r.json()["session_id"]


# ────────── happy path ──────────

async def test_empty_patch_returns_current_tags(client):
    sid = await _seed(client)
    r = await client.patch(f"/v4/sessions/{sid}/tags", json={})
    assert r.status_code == 200
    assert r.json() == {"session_id": sid, "tags": {}}


async def test_set_creates_tags(client):
    sid = await _seed(client)
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"project": "billing", "status": "wip"}},
    )
    assert r.status_code == 200
    assert r.json()["tags"] == {"project": "billing", "status": "wip"}


async def test_patch_preserves_unrelated_keys(client):
    """PATCH semantics: keys not in set/unset are not touched."""
    sid = await _seed(client)
    await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"project": "billing", "status": "wip", "owner": "alice"}},
    )
    # Now only update `status`; `project` and `owner` must remain.
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"status": "done"}},
    )
    assert r.json()["tags"] == {
        "project": "billing", "status": "done", "owner": "alice",
    }


async def test_unset_removes_specified_keys(client):
    sid = await _seed(client)
    await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"a": "1", "b": "2", "c": "3"}},
    )
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"unset": ["b"]},
    )
    assert r.json()["tags"] == {"a": "1", "c": "3"}


async def test_unset_missing_key_is_noop(client):
    sid = await _seed(client)
    await client.patch(f"/v4/sessions/{sid}/tags", json={"set": {"a": "1"}})
    r = await client.patch(f"/v4/sessions/{sid}/tags", json={"unset": ["nope"]})
    assert r.status_code == 200
    assert r.json()["tags"] == {"a": "1"}


async def test_set_and_unset_in_one_call(client):
    sid = await _seed(client)
    await client.patch(f"/v4/sessions/{sid}/tags",
                       json={"set": {"old": "x", "keep": "y"}})
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"new": "z"}, "unset": ["old"]},
    )
    assert r.json()["tags"] == {"keep": "y", "new": "z"}


# ────────── validation ──────────

async def test_invalid_key_rejected(client):
    sid = await _seed(client)
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"1bad": "x"}},
    )
    assert r.status_code == 400
    assert "invalid" in r.json()["detail"].lower()


async def test_value_too_long_rejected(client):
    sid = await _seed(client)
    big = "x" * (MAX_VALUE_LEN + 1)
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"k": big}},
    )
    assert r.status_code == 400


async def test_too_many_tags_rejected(client):
    sid = await _seed(client)
    payload = {f"k{i}": "v" for i in range(MAX_TAGS_PER_OBJECT + 1)}
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": payload},
    )
    assert r.status_code == 400


async def test_set_and_unset_same_key_rejected(client):
    sid = await _seed(client)
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"k": "v"}, "unset": ["k"]},
    )
    assert r.status_code == 400


async def test_validation_does_not_partially_apply(client):
    """If one key in `set` is bad, the whole PATCH must roll back —
    other (valid) keys in the same payload must NOT land."""
    sid = await _seed(client)
    await client.patch(f"/v4/sessions/{sid}/tags",
                       json={"set": {"existing": "x"}})
    r = await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"valid": "y", "1bad": "z"}},
    )
    assert r.status_code == 400
    cur = (await client.patch(f"/v4/sessions/{sid}/tags", json={})).json()
    assert cur["tags"] == {"existing": "x"}, "valid key must not have landed"


# ────────── not found ──────────

async def test_404_on_missing_session(client):
    r = await client.patch(
        "/v4/sessions/sess-deadbeef-nope/tags",
        json={"set": {"x": "y"}},
    )
    assert r.status_code == 404


# ────────── meta.json mirror ──────────

async def _read_meta(app, source: str, sid: str) -> dict:
    """Resolve the on-disk meta.json for a session and parse it."""
    return await app.state.db.sessions.read_meta(source, sid) or {}


async def test_patch_mirrors_tags_to_meta_json(client, app):
    """PATCH /tags must write the same dict into meta.json — the file
    is v3's audit / portability mirror; user-supplied tags belong in
    the same persistence tier as ``metadata`` / ``round_count``."""
    sid = await _seed(client)
    await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"project": "billing", "status": "wip"}},
    )
    meta = await _read_meta(app, "claude-code", sid)
    assert meta.get("tags") == {"project": "billing", "status": "wip"}


async def test_create_writes_empty_tags_to_meta_json(client, app):
    """Even with no PATCH, a freshly created session's meta.json should
    carry ``tags: {}`` so the file's shape is uniform."""
    sid = await _seed(client)
    meta = await _read_meta(app, "claude-code", sid)
    assert meta.get("tags") == {}


async def test_append_after_patch_preserves_tags(client, app):
    """A PATCH followed by another ingest (append) must NOT lose the
    tags from meta.json. _refresh_meta has to read current tags from
    SQLite and carry them through, otherwise the audit file goes
    stale on every append."""
    sid = await _seed(client)
    await client.patch(
        f"/v4/sessions/{sid}/tags",
        json={"set": {"project": "billing"}},
    )
    # Ingest more rounds — same upstream id, second append.
    r = await ingest_session(client, "t-1", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hi"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "hello"}]},
    ])
    r.raise_for_status()
    meta = await _read_meta(app, "claude-code", sid)
    assert meta.get("tags") == {"project": "billing"}, (
        "tags lost on append — _refresh_meta isn't carrying them forward"
    )
