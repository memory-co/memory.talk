"""links -- CardLinkStore: l<n> mint, target_type derive, idempotent, out/in. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.cards import CardStore
from memorytalk.repository.card_links import CardLinkStore


@pytest.fixture
def cards(v4db):
    return CardStore(v4db.conn, v4db.storage)


@pytest.fixture
def links(v4db):
    return CardLinkStore(v4db.conn, v4db.storage)


async def test_insert_mints_card_scoped_seq(cards, links):
    await cards.insert("card_1", "issue?", "t")
    l1 = await links.insert("card_1", "specializes", "card_2", "narrower case", "t")
    l2 = await links.insert("card_1", "related", "card_3", "see also", "t")
    assert l1 == "l1" and l2 == "l2"
    assert (await cards.get("card_1"))["link_count"] == 2


async def test_insert_derives_target_type_card(cards, links):
    await cards.insert("card_1", "issue?", "t")
    await links.insert("card_1", "specializes", "card_2", "c", "t")
    out = await links.list_out("card_1")
    assert out[0]["target_type"] == "card"
    assert out[0]["claim"] == "c"


async def test_insert_derives_target_type_position(cards, links):
    await cards.insert("card_1", "issue?", "t")
    await links.insert("card_1", "suggested_by", "card_9#p2", "from that answer", "t")
    out = await links.list_out("card_1")
    assert out[0]["target_type"] == "position"


async def test_insert_is_idempotent(cards, links):
    await cards.insert("card_1", "issue?", "t")
    a = await links.insert("card_1", "specializes", "card_2", "c", "t")
    b = await links.insert("card_1", "specializes", "card_2", "c2", "t2")  # same edge
    assert a == b == "l1"
    assert len(await links.list_out("card_1")) == 1
    assert (await cards.get("card_1"))["link_count"] == 1  # not bumped twice


async def test_list_in_reverse(cards, links):
    await cards.insert("card_1", "issue?", "t")
    await links.insert("card_1", "replaces", "card_2", "supersedes it", "t")
    incoming = await links.list_in("card_2")
    assert incoming[0]["card_id"] == "card_1"
    assert incoming[0]["type"] == "replaces"


async def test_bump_argument(cards, links):
    await cards.insert("card_1", "issue?", "t")
    link = await links.insert("card_1", "specializes", "card_2", "c", "t")
    await links.bump_argument("card_1", link, 1)
    await links.bump_argument("card_1", link, 0)
    row = await links.get("card_1", link)
    assert row["up_count"] == 1 and row["neutral_count"] == 1 and row["review_count"] == 2
