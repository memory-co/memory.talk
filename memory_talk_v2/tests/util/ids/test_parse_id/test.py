"""util.ids — parse_id() splits prefixed string into (IdKind, raw); rejects unknown prefix."""
from __future__ import annotations

import pytest

from memory_talk_v2.util.ids import IdKind, InvalidIdError, parse_id


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
