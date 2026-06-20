"""reviews -- ReviewStore insert (target/target_kind) / list / count. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.reviews import ReviewStore, target_kind_of


@pytest.fixture
def reviews(v4db):
    return ReviewStore(v4db.conn)


def test_target_kind_derive():
    assert target_kind_of("p1") == "position"
    assert target_kind_of("l3") == "link"
    with pytest.raises(ValueError):
        target_kind_of("card_x")


async def test_insert_then_list_for_target(reviews):
    # args: review_id, card_id, target, target_kind, session_id, indexes, argument, comment, created_at
    await reviews.insert(
        "review_1", "card_1", "p1", "position", "sess-a", "1-3", 1, "validated",
        "2026-06-01T00:00:00Z")
    await reviews.insert(
        "review_2", "card_1", "p1", "position", "sess-b", "4-5", -1, None,
        "2026-06-02T00:00:00Z")
    rows = await reviews.list_for_target("card_1", "p1")
    assert [r["review_id"] for r in rows] == ["review_2", "review_1"]  # newest first
    assert rows[0]["argument"] == -1
    assert rows[0]["target_kind"] == "position"


async def test_list_scoped_to_target(reviews):
    await reviews.insert("review_1", "card_1", "p1", "position", "sess-a", "1", 1, None, "t")
    await reviews.insert("review_2", "card_1", "p2", "position", "sess-a", "1", 1, None, "t")
    await reviews.insert("review_3", "card_1", "l1", "link", "sess-a", "1", 1, None, "t")
    assert len(await reviews.list_for_target("card_1", "p1")) == 1
    assert len(await reviews.list_for_target("card_1", "l1")) == 1


async def test_list_for_card(reviews):
    await reviews.insert("review_1", "card_1", "p1", "position", "sess-a", "1", 1, None, "t")
    await reviews.insert("review_2", "card_1", "l1", "link", "sess-a", "1", 1, None, "t")
    await reviews.insert("review_3", "card_2", "p1", "position", "sess-a", "1", 1, None, "t")
    assert len(await reviews.list_for_card("card_1")) == 2


async def test_exists_and_count(reviews):
    assert await reviews.exists("review_1") is False
    await reviews.insert("review_1", "card_1", "p1", "position", "sess-a", "1", 0, None, "t")
    assert await reviews.exists("review_1") is True
    assert await reviews.count() == 1
