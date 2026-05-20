"""IngestService — append-only semantics through POST /v3/sessions.

The legacy v2 merge protocol (per-round content-hash diff + overwrite
detection) is gone; the new model is append-only with optimistic
concurrency on ``sessions.last_round_id``. The HTTP route still accepts
whole-session payloads as a fixture/convenience: it filters the input
list to rounds strictly after the server's current cursor and appends
those.
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
    assert body["added_count"] == 2


async def test_resending_same_rounds_is_skipped(client):
    """Once r1/r2 are stored, posting the same payload again finds no
    rounds after the cursor — nothing to append, action=skipped."""
    await client.post("/v3/sessions", json=_make_session())
    r = await client.post("/v3/sessions", json=_make_session())
    body = r.json()
    assert body["action"] == "skipped"
    assert body["added_count"] == 0
    assert body["round_count"] == 2


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


async def test_changed_content_for_existing_round_id_is_ignored(client):
    """v3 is strictly append-only. The wrapper filters the input on
    round_id, so the cursor still matches r2 in the rewritten payload
    and r2 itself is treated as already-stored — its mutated content is
    silently discarded, no overwrite event, no replacement on disk."""
    await client.post("/v3/sessions", json=_make_session())
    rewritten = _make_session(sha="sha2", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hello world"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "OVERWRITTEN"}]},
    ])
    r = await client.post("/v3/sessions", json=rewritten)
    assert r.json()["action"] == "skipped"

    r = await client.post("/v3/read", json={"id": "sess_abc-123"})
    rounds = r.json()["session"]["rounds"]
    a_round = next(r for r in rounds if r["index"] == 2)
    assert "hi back" in a_round["content"][0]["text"], (
        "original content for r2 must be preserved (append-only)"
    )


async def test_divergent_payload_missing_cursor_yields_nothing(client):
    """If the input payload doesn't contain the round_id the server is
    currently parked at, we can't safely tell which rounds are 'new'.
    Treat the whole batch as not-new (no append, no error)."""
    await client.post("/v3/sessions", json=_make_session())
    # New payload doesn't reference r2 at all — diverged history.
    divergent = _make_session(sha="sha9", rounds=[
        {"round_id": "X1", "role": "human",
         "content": [{"type": "text", "text": "fresh tree"}]},
        {"round_id": "X2", "role": "assistant",
         "content": [{"type": "text", "text": "no relation"}]},
    ])
    r = await client.post("/v3/sessions", json=divergent)
    body = r.json()
    assert body["action"] == "skipped"
    assert body["round_count"] == 2  # unchanged from before
