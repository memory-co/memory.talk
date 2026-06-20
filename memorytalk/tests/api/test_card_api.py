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
    pos = r.json()["position"]
    assert pos == "p1"
    # GET positions reflects it (addressed id surfaced)
    g = await client.get(f"/v4/cards/{cid}/positions")
    assert g.status_code == 200
    assert g.json()["positions"][0]["position"] == pos
    assert g.json()["positions"][0]["id"] == f"{cid}#{pos}"


async def test_position_on_missing_card_404(client):
    r = await client.post("/v4/cards/card_nope/positions", json={"claim": "x"})
    assert r.status_code == 404


async def test_review_bumps_and_read_sorts_by_credence(client):
    sid = await _session(client)
    cid = await _card(client)
    p_lo = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "MySQL"})).json()["position"]
    p_hi = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "LanceDB"})).json()["position"]
    for ix in ("1", "2"):
        r = await client.post(f"/v4/cards/{cid}/positions/{p_hi}/reviews", json={
            "session_id": sid, "indexes": ix, "argument": 1})
        assert r.status_code == 200, r.text
        assert r.json()["target_kind"] == "position"
    r = await client.post(f"/v4/cards/{cid}/positions/{p_lo}/reviews", json={
        "session_id": sid, "indexes": "3", "argument": -1})
    assert r.status_code == 200
    # read card → current answer (highest credence) first
    rd = await client.post("/v4/read", json={"id": cid})
    assert rd.status_code == 200
    body = rd.json()
    assert body["type"] == "card"
    assert body["card"]["positions"][0]["position"] == p_hi
    assert body["card"]["positions"][0]["credence"] == 2
    # read the position directly via fragment → reviews attached
    rp = await client.post("/v4/read", json={"id": f"{cid}#{p_hi}"})
    assert rp.json()["type"] == "position"
    assert rp.json()["position"]["up_count"] == 2
    assert len(rp.json()["position"]["reviews"]) == 2


async def test_review_bad_argument_422(client):
    sid = await _session(client)
    cid = await _card(client)
    pos = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "x"})).json()["position"]
    r = await client.post(f"/v4/cards/{cid}/positions/{pos}/reviews", json={
        "session_id": sid, "indexes": "1", "argument": 5})
    assert r.status_code == 422   # pydantic Literal rejects 5 before service


async def test_link_carries_claim_and_is_reviewable(client):
    sid = await _session(client)
    a = await _card(client, issue="parent question")
    b = await _card(client, issue="child question")
    r = await client.post(f"/v4/cards/{a}/links", json={
        "type": "specializes", "target_id": b, "claim": "b narrows a"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_type"] == "card" and body["link"] == "l1"
    assert body["claim"] == "b narrows a"
    # GET links surfaces claim + credence + addressed id
    g = await client.get(f"/v4/cards/{a}/links")
    assert g.json()["links"][0]["claim"] == "b narrows a"
    assert g.json()["links"][0]["id"] == f"{a}#l1"
    # review the link
    rv = await client.post(f"/v4/cards/{a}/links/l1/reviews", json={
        "session_id": sid, "indexes": "1", "argument": 1})
    assert rv.status_code == 200 and rv.json()["target_kind"] == "link"
    # read the link via fragment
    rd = await client.post("/v4/read", json={"id": f"{a}#l1"})
    assert rd.json()["type"] == "link"
    assert rd.json()["link"]["credence"] == 1
    assert len(rd.json()["link"]["reviews"]) == 1
    # read the card → link shows out, with credence
    rc = await client.post("/v4/read", json={"id": a})
    out = next(l for l in rc.json()["card"]["links"] if l["dir"] == "out")
    assert out["target_id"] == b and out["credence"] == 1


async def test_link_requires_claim_422(client):
    a = await _card(client)
    b = await _card(client)
    r = await client.post(f"/v4/cards/{a}/links", json={
        "type": "specializes", "target_id": b})
    assert r.status_code == 422   # pydantic requires claim


async def test_link_unknown_card_404(client):
    b = await _card(client)
    r = await client.post("/v4/cards/card_nope/links", json={
        "type": "related", "target_id": b, "claim": "x"})
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
    pos = (await client.post(f"/v4/cards/{cid}/positions", json={"claim": "LanceDB"})).json()["position"]
    await client.post(f"/v4/cards/{cid}/positions/{pos}/reviews", json={
        "session_id": sid, "indexes": "1", "argument": 1})
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
    # position-level provenance (--source) is reverse-lookable via the session
    assert any(row["card_id"] == cid for row in r.json()["cards"])
