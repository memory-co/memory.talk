"""v4_ids -- pos_ id mint + parse. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.util.ids import (
    POSITION_PREFIX, IdKind, InvalidIdError, new_position_id, parse_id,
)


def test_new_position_id_has_prefix():
    pid = new_position_id()
    assert pid.startswith(POSITION_PREFIX)
    assert len(pid) > len(POSITION_PREFIX)


def test_parse_position_id():
    kind, raw = parse_id("pos_01jzp3nq")
    assert kind is IdKind.POSITION
    assert raw == "01jzp3nq"


def test_parse_card_still_works():
    kind, _ = parse_id("card_01jz8k2m")
    assert kind is IdKind.CARD


def test_parse_unknown_prefix_raises():
    with pytest.raises(InvalidIdError):
        parse_id("nope_123")
