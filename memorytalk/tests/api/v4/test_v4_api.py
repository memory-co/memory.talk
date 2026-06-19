"""/v4 end-to-end — card / position / review / link / read / search / recall."""
from __future__ import annotations

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _session(client, sid="v4-src") -> str:
    rounds = [
        {"round_id": f"r{i}", "role": "human" if i % 2 else "assistant",
         "content": [{"type": "text", "text": f"round {i} about vector databases"}]}
        for i in range(1, 6)
    ]
    r = await ingest_session(client, sid, rounds=rounds)
    r.raise_for_status()
    return r.json()["session_id"]


async def _card(client, issue="Which embedded vector database should we use?") -> str:
    r = await client.post("/v4/cards", json={"issue": issue})
    assert r.status_code == 200, r.text
    return r.json()["card_id"]


# ────────── write path ──────────

async def test_create_card(client):
    r = await client.post("/v4/cards", json={"issue": "Which db?"})
    assert r.status_code == 200
    assert r.json()["card_id"].startswith("card_")


async def test_create_card_empty_issue_400(client):
    r = await client.post("/v4/cards", json={"issue": "  "})
    assert r.status_code == 400


async def test_add_position_with_source(client):
    sid = await _session(client)
    cid = await _card(client)
    r = await client.post(f"/v4/cards/{cid}/positions", json={
        "claim": "SQLite + a vector extension", "scope": "single-node",
        "source": {"session_id": sid, "indexes": "1-3"},
    })
    assert r.status_code == 200, r.text
    pid = r.json()["position_id"]
    assert pid.startswith("pos_")
    # GET positions reflects it
    g = await client.get(f"/v4/cards/{cid}/positions")
    assert g.status_code == 200
    assert g.json()["positions"][0]["position_id"] == pid
    # provenance recorded
    s = await client.get(f"/v4/cards/{cid}/sessions")
    assert s.json()["sessions"][0]["session_id"] == sid


async def test_position_on_missing_card_404(client):
    r = await client.post("/v4/cards/card_nope/positions", json={"claim": "x"})
    assert r.status_code == 404


async def test_review_bumps_and_read_sorts_by_credence(client):
    sid = await _session(client)
    cid = await _card(client)
    p_lo = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "MySQL"})).json()["position_id"]
    p_hi = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "LanceDB"})).json()["position_id"]
    for ix in ("1", "2"):
        r = await client.post(f"/v4/positions/{p_hi}/reviews", json={
            "position_id": p_hi, "session_id": sid, "indexes": ix, "argument": 1})
        assert r.status_code == 200, r.text
    r = await client.post(f"/v4/positions/{p_lo}/reviews", json={
        "position_id": p_lo, "session_id": sid, "indexes": "3", "argument": -1})
    assert r.status_code == 200
    # read card → current answer (highest credence) first
    rd = await client.post("/v4/read", json={"id": cid})
    assert rd.status_code == 200
    body = rd.json()
    assert body["type"] == "card"
    assert body["card"]["positions"][0]["position_id"] == p_hi
    assert body["card"]["positions"][0]["credence"] == 2
    # read the position directly → reviews attached
    rp = await client.post("/v4/read", json={"id": p_hi})
    assert rp.json()["position"]["up_count"] == 2
    assert len(rp.json()["position"]["reviews"]) == 2


async def test_review_bad_argument_400(client):
    sid = await _session(client)
    cid = await _card(client)
    pid = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "x"})).json()["position_id"]
    r = await client.post(f"/v4/positions/{pid}/reviews", json={
        "position_id": pid, "session_id": sid, "indexes": "1", "argument": 5})
    assert r.status_code == 422   # pydantic Literal rejects 5 before service


async def test_link_and_read(client):
    a = await _card(client, issue="parent question")
    b = await _card(client, issue="child question")
    r = await client.post(f"/v4/cards/{a}/links", json={
        "card_id": a, "type": "specializes", "target_id": b})
    assert r.status_code == 200
    assert r.json()["target_type"] == "card"
    rd = await client.post("/v4/read", json={"id": a})
    links = rd.json()["card"]["links"]
    assert any(l["dir"] == "out" and l["target_id"] == b for l in links)


async def test_link_unknown_card_404(client):
    b = await _card(client)
    r = await client.post("/v4/cards/card_nope/links", json={
        "card_id": "card_nope", "type": "related", "target_id": b})
    assert r.status_code == 404


# ────────── read-path retrieval (real dummy-embedder backend) ──────────

async def test_search_finds_card_by_issue(client):
    cid = await _card(client, issue="Which embedded vector database should we use for memory")
    await client.post(f"/v4/cards/{cid}/positions", json={"claim": "LanceDB is embedded"})
    r = await client.post("/v4/search", json={"query": "vector database", "limit": 10})
    assert r.status_code == 200, r.text
    ids = [c["card_id"] for c in r.json()["cards"]]
    assert cid in ids
    hit = next(c for c in r.json()["cards"] if c["card_id"] == cid)
    assert hit["top_position"]["claim"] == "LanceDB is embedded"


async def test_search_empty_query_lists(client):
    c1 = await _card(client, issue="alpha")
    c2 = await _card(client, issue="beta")
    r = await client.post("/v4/search", json={"query": "", "limit": 50})
    ids = [c["card_id"] for c in r.json()["cards"]]
    assert c1 in ids and c2 in ids


async def test_search_bad_limit_400(client):
    r = await client.post("/v4/search", json={"query": "x", "limit": 9999})
    assert r.status_code == 400


async def test_recall_returns_answer(client):
    sid = await _session(client)
    cid = await _card(client, issue="Which embedded vector database for the memory layer")
    pid = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "LanceDB"})).json()["position_id"]
    await client.post(f"/v4/positions/{pid}/reviews", json={
        "position_id": pid, "session_id": sid, "indexes": "1", "argument": 1})
    r = await client.post("/v4/recall", json={"session_id": sid, "prompt": "vector database choice"})
    assert r.status_code == 200, r.text
    cards = r.json()["cards"]
    assert any(c["card_id"] == cid and c["answer"]["claim"] == "LanceDB" for c in cards)


async def test_recall_dedups_within_session(client):
    sid = await _session(client)
    cid = await _card(client, issue="Which embedded vector database for memory layer dedup")
    await client.post(f"/v4/cards/{cid}/positions", json={"claim": "LanceDB"})
    first = await client.post("/v4/recall", json={"session_id": sid, "prompt": "vector database"})
    assert any(c["card_id"] == cid for c in first.json()["cards"])
    second = await client.post("/v4/recall", json={"session_id": sid, "prompt": "vector database"})
    assert all(c["card_id"] != cid for c in second.json()["cards"])   # already recalled


async def test_recall_bad_session_prefix_400(client):
    r = await client.post("/v4/recall", json={"session_id": "card_x", "prompt": "q"})
    assert r.status_code == 400


async def test_session_reverse_lookup(client):
    sid = await _session(client)
    cid = await _card(client)
    await client.post(f"/v4/cards/{cid}/positions", json={
        "claim": "x", "source": {"session_id": sid, "indexes": "1"}})
    r = await client.get(f"/v4/sessions/{sid}/cards")
    assert r.status_code == 200
    assert any(row["card_id"] == cid for row in r.json()["cards"])
