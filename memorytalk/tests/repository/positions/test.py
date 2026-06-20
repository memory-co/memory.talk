"""positions -- card-scoped p<n> mint, row + file, argument bump, list. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.cards import CardStore
from memorytalk.repository.positions import PositionStore


@pytest.fixture
def cards(v4db):
    return CardStore(v4db.conn, v4db.storage)


@pytest.fixture
def positions(v4db):
    return PositionStore(v4db.conn, v4db.storage)


async def test_insert_mints_card_scoped_seq(cards, positions):
    await cards.insert("card_1", "issue?", "t")
    p1 = await positions.insert("card_1", "be concise", "t", scope="daily")
    p2 = await positions.insert("card_1", "it depends", "t", forked_from="p1")
    assert p1 == "p1" and p2 == "p2"
    # counter bumped on cards
    assert (await cards.get("card_1"))["position_count"] == 2


async def test_insert_then_get(cards, positions):
    await cards.insert("card_1", "issue?", "t")
    pos = await positions.insert("card_1", "be concise", "t", scope="daily")
    row = await positions.get("card_1", pos)
    assert row["claim"] == "be concise"
    assert row["scope"] == "daily"
    assert row["forked_from"] is None
    assert row["up_count"] == 0 and row["review_count"] == 0


async def test_seq_is_per_card(cards, positions):
    await cards.insert("card_1", "a?", "t")
    await cards.insert("card_2", "b?", "t")
    assert await positions.insert("card_1", "x", "t") == "p1"
    assert await positions.insert("card_2", "y", "t") == "p1"  # independent seq
    assert await positions.insert("card_1", "z", "t") == "p2"


async def test_write_doc_round_trip(positions):
    await positions.write_doc(
        "card_1", {"position": "p1", "claim": "x", "created_at": "t"})
    doc = await positions.read_doc("card_1", "p1")
    assert doc["claim"] == "x"


async def test_bump_argument_up(cards, positions):
    await cards.insert("card_1", "issue?", "t")
    pos = await positions.insert("card_1", "x", "t")
    await positions.bump_argument("card_1", pos, 1)
    await positions.bump_argument("card_1", pos, 1)
    await positions.bump_argument("card_1", pos, -1)
    await positions.bump_argument("card_1", pos, 0)
    row = await positions.get("card_1", pos)
    assert row["up_count"] == 2 and row["down_count"] == 1 and row["neutral_count"] == 1
    assert row["review_count"] == 4  # total = up+down+neutral


async def test_bump_argument_rejects_bad_value(cards, positions):
    await cards.insert("card_1", "issue?", "t")
    pos = await positions.insert("card_1", "x", "t")
    with pytest.raises(ValueError):
        await positions.bump_argument("card_1", pos, 2)


async def test_list_for_card(cards, positions):
    await cards.insert("card_1", "a?", "t")
    await cards.insert("card_2", "b?", "t")
    await positions.insert("card_1", "a", "t")
    await positions.insert("card_1", "b", "t")
    await positions.insert("card_2", "c", "t")
    rows = await positions.list_for_card("card_1")
    assert {r["position"] for r in rows} == {"p1", "p2"}
