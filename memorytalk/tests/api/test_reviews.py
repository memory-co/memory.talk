"""POST /v3/reviews — validation + stats bump + persistence + events."""
from __future__ import annotations
import json
import pytest

pytestmark = pytest.mark.asyncio


async def _ingest(client, sid: str = "rev-src") -> str:
    r = await client.post("/v3/sessions", json={
        "session_id": sid, "source": "claude-code",
        "created_at": "2026-05-18T09:00:00Z",
        "metadata": {"cwd": "/work/proj"},
        "sha256": f"sha-{sid}",
        "rounds": [
            {"round_id": f"r{i}", "role": "human" if i % 2 else "assistant",
             "content": [{"type": "text", "text": f"round {i} text"}]}
            for i in range(1, 6)
        ],
    })
    r.raise_for_status()
    return r.json()["session_id"]


async def _make_card(client, sid: str, insight: str = "the claim") -> str:
    r = await client.post("/v3/cards", json={
        "insight": insight,
        "rounds": [{"session_id": sid, "indexes": "1-2"}],
    })
    r.raise_for_status()
    return r.json()["card_id"]


async def test_review_create_basic(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    r = await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid,
        "indexes": "3", "score": 1, "comment": "still stands",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["review_id"].startswith("review_")
    assert body["card_id"] == cid
    assert body["score"] == 1


async def test_review_bumps_card_stats_correctly(app, client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    db = app.state.db
    await client.post("/v3/read", json={"id": cid})
    stats0 = await db.cards.get_stats(cid)
    assert stats0["review_count"] == 0

    await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "1", "score": 1,
    })
    s = await db.cards.get_stats(cid)
    assert s["review_up"] == 1
    assert s["review_down"] == 0
    assert s["review_neutral"] == 0
    assert s["review_count"] == 1

    await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "2", "score": -1,
    })
    s = await db.cards.get_stats(cid)
    assert s["review_up"] == 1
    assert s["review_down"] == 1
    assert s["review_count"] == 2

    await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "3", "score": 0,
    })
    s = await db.cards.get_stats(cid)
    assert s["review_neutral"] == 1
    assert s["review_count"] == 3


async def test_review_appears_in_read_card_response(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "3-4",
        "score": 1, "comment": "confirmed",
    })
    r = await client.post("/v3/read", json={"id": cid})
    body = r.json()
    assert body["card"]["stats"]["review_up"] == 1
    reviews = body["card"]["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["comment"] == "confirmed"
    assert reviews[0]["indexes"] == "3-4"
    assert reviews[0]["score"] == 1


async def test_review_card_not_found(client):
    sid = await _ingest(client)
    r = await client.post("/v3/reviews", json={
        "card_id": "card_doesnotexist", "session_id": sid,
        "indexes": "1", "score": 1,
    })
    assert r.status_code == 400
    assert "not found" in r.json()["detail"]


async def test_review_session_not_found(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    r = await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": "sess_nope",
        "indexes": "1", "score": 1,
    })
    assert r.status_code == 400


async def test_review_index_out_of_range(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    r = await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "99", "score": 1,
    })
    assert r.status_code == 400
    assert "out of range" in r.json()["detail"]


async def test_review_invalid_score_rejected_by_pydantic(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    r = await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "1", "score": 5,
    })
    assert r.status_code == 422


async def test_review_multiple_pairs_per_card_session(app, client):
    """Same (card_id, session_id) is intentionally allowed multiple reviews
    (different indexes / different stances). Each lands as its own row."""
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "1", "score": -1,
        "comment": "first take",
    })
    await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "3-4", "score": 1,
        "comment": "later: i was wrong",
    })
    rows = await app.state.db.reviews.list_for_card(cid)
    assert len(rows) == 2
    stats = await app.state.db.cards.get_stats(cid)
    assert stats["review_up"] == 1
    assert stats["review_down"] == 1
    assert stats["review_count"] == 2


async def test_review_emits_event_to_card_jsonl(client, data_root):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "1", "score": 1,
    })
    raw = cid[len("card_"):]
    bucket = raw[:2].lower()
    evt = data_root / "cards" / bucket / cid / "events.jsonl"
    assert evt.exists()
    events = [json.loads(l) for l in evt.read_text().splitlines() if l.strip()]
    kinds = [e["event"] for e in events]
    assert "reviewed" in kinds
    reviewed = next(e for e in events if e["event"] == "reviewed")
    assert reviewed["score"] == 1
    assert reviewed["session_id"] == sid
