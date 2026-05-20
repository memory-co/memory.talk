"""POST /v3/cards — create + validation + persistence."""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _ingest_session(client, sid: str = "src-1") -> str:
    """Ingest a session that has 5 rounds so cards can pull slices."""
    rounds = [
        {"round_id": f"r{i}", "role": "human" if i % 2 else "assistant",
         "content": [{"type": "text", "text": f"round {i} body about LanceDB"}]}
        for i in range(1, 6)
    ]
    r = await ingest_session(client, sid, rounds=rounds)
    r.raise_for_status()
    return r.json()["session_id"]


async def test_card_create_basic(client):
    sid = await _ingest_session(client)
    r = await client.post("/v3/cards", json={
        "insight": "选定 LanceDB 做向量存储",
        "rounds": [{"session_id": sid, "indexes": "1-3"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["card_id"].startswith("card_")


async def test_card_create_read_roundtrip(client):
    sid = await _ingest_session(client)
    r = await client.post("/v3/cards", json={
        "insight": "embedded vector db pick",
        "rounds": [{"session_id": sid, "indexes": "2,4"}],
    })
    cid = r.json()["card_id"]

    r = await client.post("/v3/read", json={"id": cid})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "card"
    c = body["card"]
    assert c["insight"] == "embedded vector db pick"
    assert len(c["rounds"]) == 2
    indices = sorted(r["index"] for r in c["rounds"])
    assert indices == [2, 4]
    # stats initialized to zeros (read just bumped read_count by 1).
    assert c["stats"]["read_count"] == 1
    assert c["stats"]["review_count"] == 0


async def test_card_with_explicit_id(client):
    sid = await _ingest_session(client)
    r = await client.post("/v3/cards", json={
        "card_id": "card_explicit_xyz",
        "insight": "explicit id card",
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    assert r.status_code == 200
    assert r.json()["card_id"] == "card_explicit_xyz"


async def test_card_duplicate_id_returns_409(client):
    sid = await _ingest_session(client)
    base = {
        "card_id": "card_dup_xyz",
        "insight": "first",
        "rounds": [{"session_id": sid, "indexes": "1"}],
    }
    r = await client.post("/v3/cards", json=base)
    assert r.status_code == 200
    base["insight"] = "second attempt"
    r = await client.post("/v3/cards", json=base)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


async def test_card_invalid_card_id_prefix(client):
    sid = await _ingest_session(client)
    r = await client.post("/v3/cards", json={
        "card_id": "wrong_prefix_xyz",
        "insight": "x",
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    assert r.status_code == 400


async def test_card_invalid_session_id_prefix(client):
    r = await client.post("/v3/cards", json={
        "insight": "x",
        "rounds": [{"session_id": "garbage", "indexes": "1"}],
    })
    assert r.status_code == 400


async def test_card_session_not_found(client):
    r = await client.post("/v3/cards", json={
        "insight": "x",
        "rounds": [{"session_id": "sess_nonexistent", "indexes": "1"}],
    })
    assert r.status_code == 400
    assert "not found" in r.json()["detail"]


async def test_card_index_out_of_range(client):
    sid = await _ingest_session(client)  # 5 rounds
    r = await client.post("/v3/cards", json={
        "insight": "x",
        "rounds": [{"session_id": sid, "indexes": "10"}],
    })
    assert r.status_code == 400
    assert "out of range" in r.json()["detail"]


async def test_card_indexes_must_be_monotonic(client):
    sid = await _ingest_session(client)
    r = await client.post("/v3/cards", json={
        "insight": "x",
        "rounds": [{"session_id": sid, "indexes": "3,1"}],
    })
    assert r.status_code == 400


async def test_card_source_cards_unknown_relation(client):
    sid = await _ingest_session(client)
    r1 = await client.post("/v3/cards", json={
        "insight": "parent",
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    parent = r1.json()["card_id"]
    r = await client.post("/v3/cards", json={
        "insight": "child",
        "rounds": [{"session_id": sid, "indexes": "2"}],
        "source_cards": [{"card_id": parent, "relation": "nonsense"}],
    })
    assert r.status_code in (400, 422)


async def test_card_source_card_not_found_returns_400(client):
    sid = await _ingest_session(client)
    r = await client.post("/v3/cards", json={
        "insight": "x",
        "rounds": [{"session_id": sid, "indexes": "1"}],
        "source_cards": [
            {"card_id": "card_missing", "relation": "supersedes"},
        ],
    })
    assert r.status_code == 400
    assert "not found" in r.json()["detail"]


async def test_card_with_source_cards_persists_edges(app, client):
    sid = await _ingest_session(client)
    rp = await client.post("/v3/cards", json={
        "insight": "the old idea",
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    parent = rp.json()["card_id"]

    rc = await client.post("/v3/cards", json={
        "insight": "the new revised idea",
        "rounds": [{"session_id": sid, "indexes": "2"}],
        "source_cards": [{"card_id": parent, "relation": "supersedes"}],
    })
    child = rc.json()["card_id"]

    r = await client.post("/v3/read", json={"id": child})
    body = r.json()
    assert len(body["card"]["source_cards"]) == 1
    assert body["card"]["source_cards"][0]["card_id"] == parent
    assert body["card"]["source_cards"][0]["relation"] == "supersedes"


async def test_card_writes_to_lancedb_for_search(client):
    sid = await _ingest_session(client)
    r = await client.post("/v3/cards", json={
        "insight": "搜索关键词 LanceDB 出现在 insight 里",
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    cid = r.json()["card_id"]
    r = await client.post("/v3/search", json={"query": "LanceDB"})
    body = r.json()
    card_results = [it for it in body["results"] if it["type"] == "card"]
    assert any(c["card_id"] == cid for c in card_results)


async def test_card_empty_rounds_is_allowed(client):
    """A synthetic card with no source-session rounds is valid (it's a
    distillation from other cards, or a top-down assertion)."""
    r = await client.post("/v3/cards", json={
        "insight": "Synthetic card with no source rounds",
        "rounds": [],
    })
    assert r.status_code == 200


async def test_card_missing_insight_returns_400(client):
    r = await client.post("/v3/cards", json={"insight": "", "rounds": []})
    assert r.status_code == 400
    assert "insight" in r.json()["detail"]
