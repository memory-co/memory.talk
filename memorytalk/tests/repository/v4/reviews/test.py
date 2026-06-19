"""reviews -- V4ReviewStore insert / list_for_position / count. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.reviews import V4ReviewStore


@pytest.fixture
def reviews(v4db):
    return V4ReviewStore(v4db.conn)


async def test_insert_then_list(reviews):
    # insert args: review_id, position_id, card_id, session_id, indexes, argument, comment, created_at
    await reviews.insert(
        "review_1", "pos_1", "card_1", "sess-a", "1-3", 1, "validated", "2026-06-01T00:00:00Z")
    await reviews.insert(
        "review_2", "pos_1", "card_1", "sess-b", "4-5", -1, None, "2026-06-02T00:00:00Z")
    rows = await reviews.list_for_position("pos_1")
    assert [r["review_id"] for r in rows] == ["review_2", "review_1"]  # newest first
    assert rows[0]["argument"] == -1
    assert rows[0]["card_id"] == "card_1"


async def test_list_scoped_to_position(reviews):
    await reviews.insert("review_1", "pos_1", "card_1", "sess-a", "1", 1, None, "t")
    await reviews.insert("review_2", "pos_2", "card_1", "sess-a", "1", 1, None, "t")
    assert len(await reviews.list_for_position("pos_1")) == 1


async def test_exists_and_count(reviews):
    assert await reviews.exists("review_1") is False
    await reviews.insert("review_1", "pos_1", "card_1", "sess-a", "1", 0, None, "t")
    assert await reviews.exists("review_1") is True
    assert await reviews.count() == 1
