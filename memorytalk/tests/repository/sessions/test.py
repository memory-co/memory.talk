"""sessions -- CardSessionStore provenance + reverse lookup. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.card_sessions import CardSessionStore


@pytest.fixture
def sessions(v4db):
    return CardSessionStore(v4db.conn)


async def test_insert_then_list_for_card(sessions):
    # insert args: card_id, session_id, position_id, indexes, created_at
    await sessions.insert("card_1", "sess-a", "pos_1", "11-15", "t")
    rows = await sessions.list_for_card("card_1")
    assert rows[0]["session_id"] == "sess-a"
    assert rows[0]["position_id"] == "pos_1"
    assert rows[0]["indexes"] == "11-15"


async def test_multi_session_per_card(sessions):
    await sessions.insert("card_1", "sess-a", "", "1-3", "t")   # "" = card-level
    await sessions.insert("card_1", "sess-b", "", "4-5", "t")
    assert len(await sessions.list_for_card("card_1")) == 2


async def test_same_card_session_different_position(sessions):
    # PK includes position_id -> same card+session, two positions = 2 rows
    await sessions.insert("card_1", "sess-a", "pos_1", "1-3", "t")
    await sessions.insert("card_1", "sess-a", "pos_2", "4-5", "t")
    assert len(await sessions.list_for_card("card_1")) == 2


async def test_reverse_list_cards_for_session(sessions):
    await sessions.insert("card_1", "sess-a", "", "1-3", "t")
    await sessions.insert("card_2", "sess-a", "", "7-9", "t")
    cards = await sessions.list_cards_for_session("sess-a")
    assert {c["card_id"] for c in cards} == {"card_1", "card_2"}


async def test_insert_idempotent_on_pk(sessions):
    await sessions.insert("card_1", "sess-a", "", "1-3", "t")
    await sessions.insert("card_1", "sess-a", "", "1-3", "t2")  # same (card,session,position)
    assert len(await sessions.list_for_card("card_1")) == 1
