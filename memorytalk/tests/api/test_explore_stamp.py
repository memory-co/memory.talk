"""card/review create stamps explore_id when given (advisory link, no gate)."""
from __future__ import annotations

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def test_card_create_stamps_explore_id(app, client):
    r = await client.post("/v3/cards", json={
        "insight": "lancedb is embedded", "explore_id": "explore_E1",
    })
    assert r.status_code == 200, r.text
    card_id = r.json()["card_id"]

    async with app.state.db.conn.execute(
        "SELECT explore_id FROM cards WHERE card_id = ?", (card_id,),
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == "explore_E1"


async def test_review_create_stamps_explore_id(app, client):
    # need a card + a session to review against
    r = await client.post("/v3/cards", json={"insight": "claim"})
    card_id = r.json()["card_id"]
    sr = await ingest_session(client, "rev-1", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "evidence"}]}])
    sid = sr.json()["session_id"]

    rr = await client.post("/v3/reviews", json={
        "card_id": card_id, "session_id": sid, "indexes": "1",
        "score": 1, "explore_id": "explore_E1",
    })
    assert rr.status_code == 200, rr.text
    review_id = rr.json()["review_id"]

    async with app.state.db.conn.execute(
        "SELECT explore_id FROM reviews WHERE review_id = ?", (review_id,),
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == "explore_E1"
