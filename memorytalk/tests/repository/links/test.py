"""links -- CardLinkStore: target_type derive, idempotent, out/in. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.card_links import CardLinkStore


@pytest.fixture
def links(v4db):
    return CardLinkStore(v4db.conn)


async def test_insert_derives_target_type_card(links):
    await links.insert("card_1", "specializes", "card_2", "t")
    out = await links.list_out("card_1")
    assert out[0]["target_type"] == "card"


async def test_insert_derives_target_type_position(links):
    await links.insert("card_1", "suggested_by", "pos_9", "t")
    out = await links.list_out("card_1")
    assert out[0]["target_type"] == "position"


async def test_insert_is_idempotent(links):
    await links.insert("card_1", "specializes", "card_2", "t")
    await links.insert("card_1", "specializes", "card_2", "t2")  # same edge
    assert len(await links.list_out("card_1")) == 1


async def test_list_in_reverse(links):
    await links.insert("card_1", "replaces", "card_2", "t")
    incoming = await links.list_in("card_2")
    assert incoming[0]["card_id"] == "card_1"
    assert incoming[0]["type"] == "replaces"
