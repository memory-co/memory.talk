"""IngestService — focused on the merge protocol.

Mirrors v2's ``service/test_sessions_ingest.py``: first ingest /
same-sha no-op / appended / partial_append. All paths exercised through
``POST /v3/sessions`` (no separate service-level direct call in v3 —
the ingest service is wired in the FastAPI lifespan and has no
construction shortcut).
"""
from __future__ import annotations
import pytest

pytestmark = pytest.mark.asyncio


def _make_session(session_id: str = "abc-123", sha: str = "sha1",
                  rounds: list[dict] | None = None) -> dict:
    rounds = rounds if rounds is not None else [
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hello world"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "hi back"}]},
    ]
    return {
        "session_id": session_id, "source": "claude-code",
        "created_at": "2026-05-18T09:00:00Z",
        "metadata": {"cwd": "/work/proj"},
        "sha256": sha, "rounds": rounds,
    }


async def test_first_ingest_imports(client):
    r = await client.post("/v3/sessions", json=_make_session())
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "imported"
    assert body["session_id"] == "sess_abc-123"
    assert body["round_count"] == 2


async def test_same_sha256_is_skipped(client):
    await client.post("/v3/sessions", json=_make_session())
    r = await client.post("/v3/sessions", json=_make_session())
    assert r.json()["action"] == "skipped"


async def test_appended_adds_new_rounds(client):
    await client.post("/v3/sessions", json=_make_session())
    extra = _make_session(sha="sha2", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hello world"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "hi back"}]},
        {"round_id": "r3", "role": "human",
         "content": [{"type": "text", "text": "third"}]},
    ])
    r = await client.post("/v3/sessions", json=extra)
    body = r.json()
    assert body["action"] == "appended"
    assert body["added_count"] == 1
    assert body["round_count"] == 3
    r = await client.post("/v3/read", json={"id": "sess_abc-123"})
    assert [r["index"] for r in r.json()["session"]["rounds"]] == [1, 2, 3]


async def test_overwritten_round_is_skipped_not_rewritten(client):
    """Same round_id with mutated content → skipped + reported, original
    idx still points at original content (card/review references stay stable)."""
    await client.post("/v3/sessions", json=_make_session())
    rewritten = _make_session(sha="sha2", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hello world"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "OVERWRITTEN"}]},
    ])
    r = await client.post("/v3/sessions", json=rewritten)
    body = r.json()
    assert body["action"] == "skipped"
    assert body["overwrite_skipped"] == [2]

    r = await client.post("/v3/read", json={"id": "sess_abc-123"})
    rounds = r.json()["session"]["rounds"]
    a_round = next(r for r in rounds if r["index"] == 2)
    assert "hi back" in a_round["content"][0]["text"]


async def test_partial_append_combines_new_and_overwrite(client):
    """``partial_append`` action: some new rounds AND some overwrites in one batch."""
    await client.post("/v3/sessions", json=_make_session())
    mixed = _make_session(sha="sha3", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hello world"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "MUTATED — should be skipped"}]},
        {"round_id": "r3", "role": "human",
         "content": [{"type": "text", "text": "new third round"}]},
    ])
    r = await client.post("/v3/sessions", json=mixed)
    body = r.json()
    assert body["action"] == "partial_append"
    assert body["added_count"] == 1
    assert 2 in body["overwrite_skipped"]
    assert body["round_count"] == 3
