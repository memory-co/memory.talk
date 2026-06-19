"""cards -- V4CardStore row + file round-trip, counter bumps, list. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.cards import V4CardStore


@pytest.fixture
def cards(v4db):
    return V4CardStore(v4db.conn, v4db.storage)


async def test_insert_then_get(cards):
    await cards.insert("card_01jz8k2m", "why?", "2026-06-01T00:00:00Z")
    row = await cards.get("card_01jz8k2m")
    assert row["issue"] == "why?"
    assert row["position_count"] == 0 and row["link_count"] == 0


async def test_write_doc_round_trip(cards):
    await cards.write_doc(
        {"card_id": "card_01jz8k2m", "issue": "why?", "created_at": "t"})
    doc = await cards.read_doc("card_01jz8k2m")
    assert doc["issue"] == "why?"


async def test_bump_position_count(cards):
    await cards.insert("card_01jz8k2m", "why?", "t")
    await cards.bump_position_count("card_01jz8k2m")
    await cards.bump_position_count("card_01jz8k2m")
    row = await cards.get("card_01jz8k2m")
    assert row["position_count"] == 2


async def test_bump_link_count(cards):
    await cards.insert("card_01jz8k2m", "why?", "t")
    await cards.bump_link_count("card_01jz8k2m")
    row = await cards.get("card_01jz8k2m")
    assert row["link_count"] == 1


async def test_exists_and_count(cards):
    assert await cards.exists("card_x") is False
    await cards.insert("card_x", "q", "t")
    assert await cards.exists("card_x") is True
    assert await cards.count() == 1


async def test_list_orders_by_created_desc(cards):
    await cards.insert("card_a", "qa", "2026-06-01T00:00:00Z")
    await cards.insert("card_b", "qb", "2026-06-02T00:00:00Z")
    total, rows = await cards.list_cards(limit=10)
    assert total == 2
    assert rows[0]["card_id"] == "card_b"  # newest first
