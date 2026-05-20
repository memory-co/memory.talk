"""End-to-end smoke: sync ingest → card → review → search → read.

Mirrors v2's ``api/test_writes.py`` (``test_sessions_then_cards_then_tags_then_links``)
but exercises v3's forum-dynamics pipeline instead of the v2 link/tag flow.
A single test that walks the whole chain catches regressions in the
service-layer wiring that individual focused tests would miss.
"""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def test_full_pipeline_ingest_card_review_search_read(client):
    # ── 1. sync ingest a session that mentions LanceDB ───────────────
    r = await ingest_session(client, "e2e-sess", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "we need a vector db"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "LanceDB is embedded, zero deps"}]},
        {"round_id": "r3", "role": "human",
         "content": [{"type": "text", "text": "ok, LanceDB it is"}]},
    ])
    sid = r.json()["session_id"]

    # ── 2. extract a card from rounds 2-3 ────────────────────────────
    r = await client.post("/v3/cards", json={
        "insight": "选定 LanceDB 做向量存储",
        "rounds": [{"session_id": sid, "indexes": "2-3"}],
    })
    cid = r.json()["card_id"]

    # ── 3. write a +1 review citing round 2 ──────────────────────────
    r = await client.post("/v3/reviews", json={
        "card_id": cid, "session_id": sid, "indexes": "2", "score": 1,
        "comment": "still stands three months in",
    })
    assert r.json()["status"] == "ok"

    # ── 4. search hits both the card and the session ────────────────
    r = await client.post("/v3/search", json={"query": "LanceDB"})
    body = r.json()
    types = [it["type"] for it in body["results"]]
    assert "card" in types
    assert "session" in types

    # ── 5. read the card → stats reflect the review + the read here ─
    r = await client.post("/v3/read", json={"id": cid})
    c = r.json()["card"]
    assert c["stats"]["review_up"] == 1
    assert c["stats"]["review_count"] == 1
    assert c["stats"]["read_count"] == 1
    # The review materialized in the card's response.
    assert len(c["reviews"]) == 1
    assert c["reviews"][0]["comment"] == "still stands three months in"
    # The card's rounds were expanded from the source session.
    assert {r["index"] for r in c["rounds"]} == {2, 3}
