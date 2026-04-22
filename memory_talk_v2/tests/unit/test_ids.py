import pytest

from memory_talk_v2.ids import (
    CARD_PREFIX, SESSION_PREFIX, LINK_PREFIX,
    IdKind, InvalidIdError,
    new_card_id, new_link_id, new_search_id, new_event_id,
    prefix_session_id, parse_id,
)


def test_new_card_id_has_prefix():
    cid = new_card_id()
    assert cid.startswith(CARD_PREFIX)
    assert len(cid) == len(CARD_PREFIX) + 26


def test_new_link_id_has_prefix():
    assert new_link_id().startswith(LINK_PREFIX)


def test_new_search_and_event_have_prefixes():
    assert new_search_id().startswith("sch_")
    assert new_event_id().startswith("evt_")


def test_prefix_session_id_adds_prefix():
    assert prefix_session_id("187c6576-875f").startswith(SESSION_PREFIX)


def test_prefix_session_id_is_idempotent():
    already = "sess_187c6576-875f"
    assert prefix_session_id(already) == already


def test_parse_id_card():
    k, raw = parse_id("card_01jz8k2m")
    assert k == IdKind.CARD
    assert raw == "01jz8k2m"


def test_parse_id_session_link_search_event():
    assert parse_id("sess_abc")[0] == IdKind.SESSION
    assert parse_id("link_xyz")[0] == IdKind.LINK
    assert parse_id("sch_1")[0] == IdKind.SEARCH
    assert parse_id("evt_1")[0] == IdKind.EVENT


def test_parse_id_rejects_unknown_prefix():
    with pytest.raises(InvalidIdError):
        parse_id("foo_bar")


def test_ids_are_unique():
    ids = {new_card_id() for _ in range(1000)}
    assert len(ids) == 1000
