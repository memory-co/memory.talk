"""POST /v4/search — unified semantic search across the three memories.

Regression for issue #7: search must span v4 **cards + insights + session
rounds**, not just v4 cards. With the dummy embedder (deterministic per
text → identical text collides), seeding the same phrase into all three
collections lets us assert the merged, kind-tagged result stream.
"""
from __future__ import annotations
import datetime as _dt
import json as _json

import pytest

from memorytalk.searchbase import Doc
from memorytalk.service.searchbase_schema import INSIGHTS
from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def _seed_insight(app, iid: str, text: str) -> None:
    """Insert an insight row + its searchbase vector so it's retrievable."""
    db = app.state.db
    now = _now()
    await db.conn.execute(
        "INSERT INTO insights (card_id, insight, rounds, tags, created_at) "
        "VALUES (?, ?, '[]', '{}', ?)",
        (iid, text, now),
    )
    await db.conn.execute(
        "INSERT INTO insight_stats (card_id, review_up, review_down, "
        "review_neutral, review_count, read_count, updated_at) "
        "VALUES (?, 0, 0, 0, 0, 0, ?)",
        (iid, now),
    )
    await db.conn.commit()
    await app.state.searchbase.upsert(INSIGHTS, [Doc(id=iid, text=text, fields={})])


async def _make_card(client, issue: str) -> str:
    r = await client.post("/v4/cards", json={"issue": issue})
    r.raise_for_status()
    return r.json()["card_id"]


# The phrase seeded identically into all three collections — dummy
# embedder makes identical text collide, so a query of this exact phrase
# hits the card issue, the insight, and the session round alike.
PHRASE = "lancedb vector retrieval design tradeoffs"


async def test_search_spans_all_three_kinds(app, client):
    # session round carrying the phrase
    sid = (await ingest_session(client, "src-uni", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": PHRASE}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "noted"}]},
    ])).json()["session_id"]
    # insight carrying the phrase
    await _seed_insight(app, "insight_uni", PHRASE)
    # card whose issue is the phrase
    cid = await _make_card(client, PHRASE)

    r = await client.post("/v4/search", json={"query": PHRASE, "limit": 20})
    assert r.status_code == 200
    body = r.json()
    kinds = {item["kind"] for item in body["cards"]}
    assert kinds == {"card", "insight", "session"}, kinds
    # the card hit carries its card_id; the insight its insight_id; the
    # session its session_id + hits.
    card_hit = next(i for i in body["cards"] if i["kind"] == "card")
    assert card_hit["card_id"] == cid
    ins_hit = next(i for i in body["cards"] if i["kind"] == "insight")
    assert ins_hit["insight_id"] == "insight_uni"
    sess_hit = next(i for i in body["cards"] if i["kind"] == "session")
    assert sess_hit["session_id"] == sid
    assert sess_hit["hits"] and PHRASE in sess_hit["hits"][0]["text"]
    assert body["total"] == len(body["cards"])


async def test_search_returns_hits_when_zero_cards(app, client):
    """The regression that started issue #7: an install with sessions +
    insights but NO v4 cards must still return hits."""
    sid = (await ingest_session(client, "src-noc", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": PHRASE}]},
    ])).json()["session_id"]
    await _seed_insight(app, "insight_noc", PHRASE)
    # deliberately NO card created → card bucket is empty

    r = await client.post("/v4/search", json={"query": PHRASE, "limit": 20})
    assert r.status_code == 200
    body = r.json()
    kinds = {item["kind"] for item in body["cards"]}
    assert "card" not in kinds
    assert {"insight", "session"} <= kinds
    assert body["total"] >= 2


async def test_where_dsl_still_filters_cards(app, client):
    """`where` filters card answers; insight/session hits pass through."""
    # cite session must exist for review validation
    db = app.state.db
    await db.sessions.upsert(
        "sess-test0001", "claude-code", "/x", _now(), _now(), {}, 5, "r5")
    # a card whose top answer has credence 2 (PHRASE issue)
    cid = await _make_card(client, PHRASE)
    pr = await client.post(f"/v4/cards/{cid}/positions",
                           json={"claim": "use lancedb"})
    pr.raise_for_status()
    pos = pr.json()["position"]
    for ix in ("1", "2"):
        rv = await client.post(
            f"/v4/cards/{cid}/positions/{pos}/reviews",
            json={"target": f"{cid}#{pos}", "session_id": "sess-test0001",
                  "indexes": ix, "argument": 1})
        rv.raise_for_status()
    # a second card with no reviews (credence 0) on a different issue
    cid_lo = await _make_card(client, "unrelated weak question " + PHRASE)
    # an insight on the phrase (should survive the where filter)
    await _seed_insight(app, "insight_dsl", PHRASE)

    r = await client.post("/v4/search", json={
        "query": PHRASE, "where": "credence > 1", "limit": 20})
    assert r.status_code == 200
    body = r.json()
    card_ids = {i["card_id"] for i in body["cards"] if i["kind"] == "card"}
    assert cid in card_ids
    assert cid_lo not in card_ids   # credence 0 → filtered out
    # insight hit is not DSL-filtered → still present
    assert any(i["kind"] == "insight" for i in body["cards"])
