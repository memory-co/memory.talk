"""GET /v4/recall/sessions + GET /v4/recall/sessions/{sid} — list/read.

New 0.9.0 endpoints backing ``memory.talk recall list`` and
``memory.talk recall read``. Both are pure SQLite reads over
``recall_event``; the canonical ``recall.jsonl`` files aren't touched.
"""
from __future__ import annotations
import pytest

from memorytalk.adapters import get_adapter
from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _ingest(client) -> str:
    r = await ingest_session(client, "lr-src", metadata={"cwd": "/work"}, rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "intro about lancedb"}]},
    ])
    r.raise_for_status()
    return r.json()["session_id"]


async def _make_card(client, sid: str, insight: str) -> str:
    r = await client.post("/v4/insights", json={
        "insight": insight,
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    r.raise_for_status()
    return r.json()["card_id"]


def _canonical(raw: str, source: str = "claude-code") -> str:
    return get_adapter(source).mint_session_id(raw)


async def test_list_empty_when_no_recalls(client):
    r = await client.get("/v4/recall/sessions")
    assert r.status_code == 200
    assert r.json() == {"sessions": []}


async def test_list_returns_sessions_with_aggregates(client):
    sid = await _ingest(client)
    await _make_card(client, sid, "lancedb fact one")
    await _make_card(client, sid, "lancedb fact two")

    # Two hook calls in session A, one in session B.
    await client.post("/v4/recall", json={
        "source": "claude-code", "session_id": "sess-A", "prompt": "lancedb",
    })
    await client.post("/v4/recall", json={
        "source": "claude-code", "session_id": "sess-A", "prompt": "more",
    })
    await client.post("/v4/recall", json={
        "source": "claude-code", "session_id": "sess-B", "prompt": "lancedb",
    })

    r = await client.get("/v4/recall/sessions")
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    by_sid = {s["session_id"]: s for s in sessions}
    canonical_A = _canonical("sess-A")
    canonical_B = _canonical("sess-B")
    assert canonical_A in by_sid
    assert canonical_B in by_sid
    assert by_sid[canonical_A]["recalls"] == 2
    assert by_sid[canonical_A]["unique_cards"] >= 1
    assert by_sid[canonical_B]["recalls"] == 1


async def test_read_returns_events_in_order(client):
    sid = await _ingest(client)
    cid1 = await _make_card(client, sid, "alpha alpha")
    cid2 = await _make_card(client, sid, "alpha beta")

    await client.post("/v4/recall", json={
        "source": "claude-code", "session_id": "sess-read",
        "prompt": "first prompt", "top_k": 1,
    })
    await client.post("/v4/recall", json={
        "source": "claude-code", "session_id": "sess-read",
        "prompt": "second prompt", "top_k": 5,
    })

    canonical = _canonical("sess-read")
    r = await client.get(f"/v4/recall/sessions/{canonical}")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == canonical
    assert len(body["events"]) == 2
    # Default chronological order: oldest first.
    assert body["events"][0]["prompt"] == "first prompt"
    assert body["events"][1]["prompt"] == "second prompt"

    # Each event carries returned + skipped with insight snapshots.
    ev2 = body["events"][1]
    returned_ids = {c["card_id"] for c in ev2["returned"]}
    skipped_ids = {c["card_id"] for c in ev2["skipped"]}
    # Top-K=1 first run returned at most one of {cid1, cid2}; the other
    # would appear here either in returned (new) or be skipped if first
    # round picked it. At minimum cid1 or cid2 is present somewhere.
    assert (cid1 in returned_ids or cid1 in skipped_ids
            or cid2 in returned_ids or cid2 in skipped_ids)


async def test_read_reverse_flips_order(client):
    sid = await _ingest(client)
    await _make_card(client, sid, "lone match")
    for p in ("alpha", "beta", "gamma"):
        await client.post("/v4/recall", json={
            "source": "claude-code", "session_id": "sess-rev",
            "prompt": p,
        })
    canonical = _canonical("sess-rev")
    r = await client.get(
        f"/v4/recall/sessions/{canonical}?reverse=true",
    )
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
