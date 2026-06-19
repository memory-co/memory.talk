"""PATCH /v4/insights/{cid}/tags — kv tag set / unset / query.

Mirrors test_sessions_tag.py but covers card-specific concerns:
- card.json (immutable payload) must NOT be touched by tag PATCH
- tags.json sidecar IS written
- create-with-tags + later PATCH agree on the same dict shape
"""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session
from memorytalk.util.tags import MAX_TAGS_PER_OBJECT, MAX_VALUE_LEN


pytestmark = pytest.mark.asyncio


async def _seed(client) -> str:
    """Ingest a session + create a tagless card; return card_id."""
    r = await ingest_session(client, "ct-base", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hi"}]},
    ])
    r.raise_for_status()
    sid = r.json()["session_id"]
    r = await client.post("/v4/insights", json={
        "insight": "for tag tests",
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    r.raise_for_status()
    return r.json()["card_id"]


async def _read_card_doc(app, cid: str) -> dict | None:
    """Read the on-disk card.json — immutable payload."""
    return await app.state.db.insights.read_doc(cid)


async def _read_tags_file(app, cid: str) -> dict:
    return await app.state.db.insights.read_tags_file(cid)


# ────────── happy path ──────────

async def test_empty_patch_returns_current_tags(client):
    cid = await _seed(client)
    r = await client.patch(f"/v4/insights/{cid}/tags", json={})
    assert r.status_code == 200
    assert r.json() == {"card_id": cid, "tags": {}}


async def test_set_creates_tags(client):
    cid = await _seed(client)
    r = await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"project": "billing", "status": "verified"}},
    )
    assert r.status_code == 200
    assert r.json()["tags"] == {"project": "billing", "status": "verified"}


async def test_patch_preserves_unrelated_keys(client):
    cid = await _seed(client)
    await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"project": "billing", "status": "wip", "owner": "alice"}},
    )
    r = await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"status": "done"}},
    )
    assert r.json()["tags"] == {
        "project": "billing", "status": "done", "owner": "alice",
    }


async def test_unset_removes_keys(client):
    cid = await _seed(client)
    await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"a": "1", "b": "2"}},
    )
    r = await client.patch(f"/v4/insights/{cid}/tags", json={"unset": ["a"]})
    assert r.json()["tags"] == {"b": "2"}


# ────────── validation ──────────

async def test_invalid_key_rejected(client):
    cid = await _seed(client)
    r = await client.patch(f"/v4/insights/{cid}/tags", json={"set": {"1bad": "x"}})
    assert r.status_code == 400


async def test_value_too_long_rejected(client):
    cid = await _seed(client)
    r = await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"k": "x" * (MAX_VALUE_LEN + 1)}},
    )
    assert r.status_code == 400


async def test_too_many_tags_rejected(client):
    cid = await _seed(client)
    payload = {f"k{i}": "v" for i in range(MAX_TAGS_PER_OBJECT + 1)}
    r = await client.patch(f"/v4/insights/{cid}/tags", json={"set": payload})
    assert r.status_code == 400


async def test_set_and_unset_same_key_rejected(client):
    cid = await _seed(client)
    r = await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"k": "v"}, "unset": ["k"]},
    )
    assert r.status_code == 400


# ────────── not found ──────────

async def test_404_on_missing_card(client):
    r = await client.patch(
        "/v4/insights/card_nonexistent/tags",
        json={"set": {"x": "y"}},
    )
    assert r.status_code == 404


# ────────── immutable payload + sidecar mirror ──────────

async def test_card_json_not_touched_by_tag_patch(client, app):
    """card.json is the append-only payload mirror — tag PATCH must
    not write to it. Otherwise we silently invalidate the document's
    'created once, never changed' invariant."""
    cid = await _seed(client)
    before = await _read_card_doc(app, cid)
    assert before is not None
    await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"project": "billing"}},
    )
    after = await _read_card_doc(app, cid)
    assert after == before, "card.json was modified by tag PATCH"


async def test_tags_json_sidecar_written_by_patch(client, app):
    cid = await _seed(client)
    await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"project": "billing", "status": "wip"}},
    )
    sidecar = await _read_tags_file(app, cid)
    assert sidecar == {"project": "billing", "status": "wip"}


async def test_create_with_tags_writes_sidecar(client, app):
    """tags supplied on create land in both SQLite and tags.json."""
    r = await ingest_session(client, "ct-c", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hi"}]},
    ])
    r.raise_for_status()
    sid = r.json()["session_id"]
    r = await client.post("/v4/insights", json={
        "insight": "with tags from the start",
        "rounds": [{"session_id": sid, "indexes": "1"}],
        "tags": {"project": "billing"},
    })
    cid = r.json()["card_id"]
    assert await _read_tags_file(app, cid) == {"project": "billing"}


async def test_patch_overwrite_sidecar(client, app):
    """Sidecar reflects the latest PATCH'd state (PATCH semantics: only
    declared keys move; unset clears one key)."""
    cid = await _seed(client)
    await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"a": "1", "b": "2", "c": "3"}},
    )
    await client.patch(
        f"/v4/insights/{cid}/tags",
        json={"set": {"b": "TWO"}, "unset": ["c"]},
    )
    assert await _read_tags_file(app, cid) == {"a": "1", "b": "TWO"}
