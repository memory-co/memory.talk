"""POST /v3/recall — hybrid card retrieval with per-session dedup."""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _ingest(client) -> str:
    r = await ingest_session(client, "rc-src", metadata={"cwd": "/work"}, rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "intro about LanceDB"}]},
    ])
    r.raise_for_status()
    return r.json()["session_id"]


async def _make_card(client, sid: str, insight: str) -> str:
    r = await client.post("/v3/cards", json={
        "insight": insight,
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    r.raise_for_status()
    return r.json()["card_id"]


async def test_recall_basic_returns_card_with_insight(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "LanceDB is the choice")
    r = await client.post("/v3/recall", json={
        "session_id": "hook-1", "prompt": "LanceDB", "top_k": 5,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "sess_hook-1"  # normalized
    assert body["query"] == "LanceDB"
    ids = [c["card_id"] for c in body["recalled"]]
    assert cid in ids


async def test_recall_dedup_within_same_session(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "LanceDB choice")
    hook_sid = "hook-dedup-1"

    r1 = await client.post("/v3/recall", json={
        "session_id": hook_sid, "prompt": "LanceDB", "top_k": 5,
    })
    assert cid in [c["card_id"] for c in r1.json()["recalled"]]

    r2 = await client.post("/v3/recall", json={
        "session_id": hook_sid, "prompt": "LanceDB", "top_k": 5,
    })
    body2 = r2.json()
    assert cid not in [c["card_id"] for c in body2["recalled"]]
    assert cid in body2["skipped_already_recalled"]


async def test_recall_dedup_resets_for_new_session(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "lancedb take 2")
    await client.post("/v3/recall", json={
        "session_id": "hook-A", "prompt": "lancedb", "top_k": 5,
    })
    r = await client.post("/v3/recall", json={
        "session_id": "hook-B", "prompt": "lancedb", "top_k": 5,
    })
    ids = [c["card_id"] for c in r.json()["recalled"]]
    assert cid in ids


async def test_recall_bumps_recall_count(app, client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "lancedb count")
    db = app.state.db
    s0 = await db.cards.get_stats(cid)
    assert s0["recall_count"] == 0

    await client.post("/v3/recall", json={
        "session_id": "hook-count-1", "prompt": "lancedb", "top_k": 5,
    })
    s1 = await db.cards.get_stats(cid)
    assert s1["recall_count"] == 1

    # dedup'd repeat → must NOT bump.
    await client.post("/v3/recall", json={
        "session_id": "hook-count-1", "prompt": "lancedb", "top_k": 5,
    })
    s2 = await db.cards.get_stats(cid)
    assert s2["recall_count"] == 1

    # new session → fresh dedup → bumps again.
    await client.post("/v3/recall", json={
        "session_id": "hook-count-2", "prompt": "lancedb", "top_k": 5,
    })
    s3 = await db.cards.get_stats(cid)
    assert s3["recall_count"] == 2


async def test_recall_does_not_touch_search_log(app, client):
    sid = await _ingest(client)
    await _make_card(client, sid, "lancedb x")
    await client.post("/v3/recall", json={
        "session_id": "no-audit", "prompt": "lancedb",
    })
    n = await app.state.db.search_log.count()
    assert n == 0


async def test_recall_session_id_normalization(client):
    sid = await _ingest(client)
    await _make_card(client, sid, "norm-1")
    r1 = await client.post("/v3/recall", json={
        "session_id": "raw-id", "prompt": "norm",
    })
    assert r1.json()["session_id"] == "sess_raw-id"
    r2 = await client.post("/v3/recall", json={
        "session_id": "sess_already-prefixed", "prompt": "norm",
    })
    assert r2.json()["session_id"] == "sess_already-prefixed"


async def test_recall_session_in_db_not_required(client):
    sid = await _ingest(client)
    await _make_card(client, sid, "exists")
    r = await client.post("/v3/recall", json={
        "session_id": "totally-new-session-not-in-db",
        "prompt": "exists",
    })
    assert r.status_code == 200
    assert r.json()["recalled"]


async def test_recall_empty_prompt_rejected(client):
    r = await client.post("/v3/recall", json={"session_id": "x", "prompt": ""})
    assert r.status_code == 400


async def test_recall_returns_empty_when_no_matches(client):
    r = await client.post("/v3/recall", json={
        "session_id": "lonely", "prompt": "this-keyword-matches-nothing-zzz",
    })
    body = r.json()
    assert body["recalled"] == []
    assert body["skipped_already_recalled"] == []


async def test_recall_top_k_caps_returned_results(client):
    sid = await _ingest(client)
    for i in range(5):
        await _make_card(client, sid, f"lancedb fact {i}")
    r = await client.post("/v3/recall", json={
        "session_id": "cap-1", "prompt": "lancedb", "top_k": 2,
    })
    assert len(r.json()["recalled"]) <= 2
