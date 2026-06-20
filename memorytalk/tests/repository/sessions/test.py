"""sessions -- card/position/link session provenance + session_marks. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.card_sessions import CardSessionStore
from memorytalk.repository.position_sessions import PositionSessionStore
from memorytalk.repository.link_sessions import LinkSessionStore
from memorytalk.repository.session_marks import SessionMarkStore


@pytest.fixture
def sessions(v4db):
    return CardSessionStore(v4db.conn)


@pytest.fixture
def psessions(v4db):
    return PositionSessionStore(v4db.conn)


@pytest.fixture
def lsessions(v4db):
    return LinkSessionStore(v4db.conn)


@pytest.fixture
def marks(v4db):
    return SessionMarkStore(v4db.conn)


# -- card_sessions (mark + indexes) --

async def test_card_session_insert_then_list_for_card(sessions):
    # insert args: card_id, session_id, mark, indexes, created_at
    await sessions.insert("card_1", "sess-a", "m1", "36-37", "t")
    rows = await sessions.list_for_card("card_1")
    assert rows[0]["session_id"] == "sess-a"
    assert rows[0]["mark"] == "m1"
    assert rows[0]["indexes"] == "36-37"


async def test_card_session_multi_per_card(sessions):
    await sessions.insert("card_1", "sess-a", "m1", "1-3", "t")
    await sessions.insert("card_1", "sess-b", "m1", "4-5", "t")
    assert len(await sessions.list_for_card("card_1")) == 2


async def test_card_session_same_card_session_different_mark(sessions):
    # PK includes mark -> same card+session, two marks = 2 rows
    await sessions.insert("card_1", "sess-a", "m1", "1-3", "t")
    await sessions.insert("card_1", "sess-a", "m2", "4-5", "t")
    assert len(await sessions.list_for_card("card_1")) == 2


async def test_card_session_reverse_lookups(sessions):
    await sessions.insert("card_1", "sess-a", "m1", "1-3", "t")
    await sessions.insert("card_2", "sess-a", "m2", "7-9", "t")
    cards = await sessions.list_cards_for_session("sess-a")
    assert {c["card_id"] for c in cards} == {"card_1", "card_2"}
    by_mark = await sessions.list_cards_for_mark("sess-a", "m1")
    assert {c["card_id"] for c in by_mark} == {"card_1"}


async def test_card_session_idempotent_on_pk(sessions):
    await sessions.insert("card_1", "sess-a", "m1", "1-3", "t")
    await sessions.insert("card_1", "sess-a", "m1", "1-3", "t2")  # same PK
    assert len(await sessions.list_for_card("card_1")) == 1


# -- position_sessions (indexes required, mark optional) --

async def test_position_session_round_only(psessions):
    await psessions.insert("card_1", "p1", "sess-a", "11-15", "t")
    rows = await psessions.list_for_position("card_1", "p1")
    assert rows[0]["indexes"] == "11-15"
    assert rows[0]["mark"] == ""


async def test_position_session_with_mark_coexists(psessions):
    # PK includes mark: round-only row + mark-tagged row coexist
    await psessions.insert("card_1", "p1", "sess-a", "11-15", "t")
    await psessions.insert("card_1", "p1", "sess-a", "11-15", "t", mark="m1")
    assert len(await psessions.list_for_position("card_1", "p1")) == 2


async def test_position_session_reverse(psessions):
    await psessions.insert("card_1", "p1", "sess-a", "1-3", "t")
    await psessions.insert("card_2", "p1", "sess-a", "4-5", "t")
    rows = await psessions.list_positions_for_session("sess-a")
    assert {r["card_id"] for r in rows} == {"card_1", "card_2"}


# -- link_sessions --

async def test_link_session_insert_and_reverse(lsessions):
    await lsessions.insert("card_1", "l1", "sess-a", "30-34", "t")
    rows = await lsessions.list_for_link("card_1", "l1")
    assert rows[0]["indexes"] == "30-34"
    by_sess = await lsessions.list_links_for_session("sess-a")
    assert by_sess[0]["link"] == "l1"


async def test_link_session_idempotent(lsessions):
    await lsessions.insert("card_1", "l1", "sess-a", "30-34", "t")
    await lsessions.insert("card_1", "l1", "sess-a", "99", "t2")  # same PK
    assert len(await lsessions.list_for_link("card_1", "l1")) == 1


# -- session_marks (session-scoped m<n> mint + optimistic-lock baseline) --

async def test_session_mark_mints_seq(marks):
    m1 = await marks.insert("sess-a", 41, "t")
    m2 = await marks.insert("sess-a", 43, "t")
    assert m1 == "m1" and m2 == "m2"


async def test_session_mark_seq_per_session(marks):
    assert await marks.insert("sess-a", 1, "t") == "m1"
    assert await marks.insert("sess-b", 1, "t") == "m1"  # independent
    assert await marks.insert("sess-a", 2, "t") == "m2"


async def test_session_mark_get_and_list(marks):
    await marks.insert("sess-a", 41, "t")
    row = await marks.get("sess-a", "m1")
    assert row["last_index"] == 41
    assert len(await marks.list_for_session("sess-a")) == 1
