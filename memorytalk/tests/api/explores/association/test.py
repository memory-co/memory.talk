"""association — card stamps explore_id (advisory link). See README.md."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_card_create_stamps_explore_id(app, client):
    r = await client.post("/v3/insights", json={
        "insight": "lancedb is embedded", "explore_id": "explore_E1",
    })
    assert r.status_code == 200, r.text
    card_id = r.json()["card_id"]
    async with app.state.db.conn.execute(
        "SELECT explore_id FROM insights WHERE card_id = ?", (card_id,),
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == "explore_E1"
