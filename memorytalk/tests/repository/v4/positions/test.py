"""positions -- PositionStore row + file, argument bump, list_for_card. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.positions import PositionStore


@pytest.fixture
def positions(v4db):
    return PositionStore(v4db.conn, v4db.storage)


async def test_insert_then_get(positions):
    await positions.insert(
        "pos_1", "card_1", "be concise", "t", scope="daily", forked_from_position_id=None)
    row = await positions.get("pos_1")
    assert row["claim"] == "be concise"
    assert row["scope"] == "daily"
    assert row["up_count"] == 0 and row["review_count"] == 0


async def test_write_doc_round_trip(positions):
    await positions.write_doc(
        "card_1", {"position_id": "pos_1", "claim": "x", "created_at": "t"})
    doc = await positions.read_doc("card_1", "pos_1")
    assert doc["claim"] == "x"


async def test_bump_argument_up(positions):
    await positions.insert("pos_1", "card_1", "x", "t")
    await positions.bump_argument("pos_1", 1)
    await positions.bump_argument("pos_1", 1)
    await positions.bump_argument("pos_1", -1)
    await positions.bump_argument("pos_1", 0)
    row = await positions.get("pos_1")
    assert row["up_count"] == 2 and row["down_count"] == 1 and row["neutral_count"] == 1
    assert row["review_count"] == 4  # total = up+down+neutral


async def test_bump_argument_rejects_bad_value(positions):
    await positions.insert("pos_1", "card_1", "x", "t")
    with pytest.raises(ValueError):
        await positions.bump_argument("pos_1", 2)


async def test_list_for_card(positions):
    await positions.insert("pos_a", "card_1", "a", "t")
    await positions.insert("pos_b", "card_1", "b", "t")
    await positions.insert("pos_c", "card_2", "c", "t")
    rows = await positions.list_for_card("card_1")
    assert {r["position_id"] for r in rows} == {"pos_a", "pos_b"}
