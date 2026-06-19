"""GET /v4/recall/sessions + GET /v4/recall/sessions/{sid} — list/read.

Backs ``memory.talk recall list`` and ``memory.talk recall read``. Both are
pure SQLite reads over ``recall_event`` (written by the v4 card recall).
The card recall POST takes an already-canonical ``session_id`` (the hook
mints it client-side), so these tests pass ``sess-…`` ids directly.
"""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _ingest(client) -> str:
    r = await ingest_session(client, "lr-src", metadata={"cwd": "/work"}, rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "intro about lancedb"}]},
    ])
    r.raise_for_status()
    return r.json()["session_id"]


async def _make_card(client, issue: str) -> str:
    """Create a v4 card with one position so recall can surface an answer."""
    r = await client.post("/v4/cards", json={"issue": issue})
    r.raise_for_status()
    cid = r.json()["card_id"]
    await client.post(f"/v4/cards/{cid}/positions", json={"claim": issue})
    return cid


async def test_list_empty_when_no_recalls(client):
    r = await client.get("/v4/recall/sessions")
    assert r.status_code == 200
    assert r.json() == {"sessions": []}


async def test_list_returns_sessions_with_aggregates(client):
    await _make_card(client, "lancedb fact one")
    await _make_card(client, "lancedb fact two")

    # Two recalls in session A, one in session B (canonical ids).
    await client.post("/v4/recall", json={"session_id": "sess-A", "prompt": "lancedb"})
    await client.post("/v4/recall", json={"session_id": "sess-A", "prompt": "more"})
    await client.post("/v4/recall", json={"session_id": "sess-B", "prompt": "lancedb"})

    r = await client.get("/v4/recall/sessions")
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    by_sid = {s["session_id"]: s for s in sessions}
    assert "sess-A" in by_sid
    assert "sess-B" in by_sid
    assert by_sid["sess-A"]["recalls"] == 2
    assert by_sid["sess-B"]["recalls"] == 1


async def test_read_returns_events_in_order(client):
    await _make_card(client, "alpha alpha")
    await _make_card(client, "alpha beta")

    await client.post("/v4/recall", json={
        "session_id": "sess-read", "prompt": "first prompt", "top_k": 1,
    })
    await client.post("/v4/recall", json={
        "session_id": "sess-read", "prompt": "second prompt", "top_k": 5,
    })

    r = await client.get("/v4/recall/sessions/sess-read")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "sess-read"
    assert len(body["events"]) == 2
    # Default chronological order: oldest first.
    assert body["events"][0]["prompt"] == "first prompt"
    assert body["events"][1]["prompt"] == "second prompt"


async def test_read_reverse_flips_order(client):
    await _make_card(client, "lone match")
    for p in ("alpha", "beta", "gamma"):
        await client.post("/v4/recall", json={"session_id": "sess-rev", "prompt": p})
    r = await client.get("/v4/recall/sessions/sess-rev?reverse=true")
    body = r.json()
    prompts = [ev["prompt"] for ev in body["events"]]
    assert prompts == ["gamma", "beta", "alpha"]


async def test_read_missing_session_returns_empty_events(client):
    r = await client.get("/v4/recall/sessions/sess-never-existed")
    assert r.status_code == 200
    assert r.json() == {
        "session_id": "sess-never-existed",
        "events": [],
    }
