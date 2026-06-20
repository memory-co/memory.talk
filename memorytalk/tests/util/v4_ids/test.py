"""v4_ids -- card-scoped fragment ids (p<n>/l<n>/m<n>) + parse. See README.md.

Positions/CardLinks/SessionMarks have NO global prefixed id -- they are
addressed by a fragment on their parent (``card_…#p<n>`` / ``card_…#l<n>`` /
``sess…#m<n>``). ``parse_fragment`` routes both fragment ids and plain
prefixed ids.
"""
from __future__ import annotations

import pytest

from memorytalk.util.ids import (
    IdKind, InvalidIdError, link_seq, mark_seq, parse_fragment, parse_id,
    position_seq,
)


def test_seq_formatters():
    assert position_seq(3) == "p3"
    assert link_seq(2) == "l2"
    assert mark_seq(1) == "m1"


def test_parse_fragment_position():
    base, kind, seq = parse_fragment("card_01jzp3nq#p3")
    assert base == "card_01jzp3nq" and kind is IdKind.POSITION and seq == "p3"


def test_parse_fragment_link():
    base, kind, seq = parse_fragment("card_01jzp3nq#l2")
    assert base == "card_01jzp3nq" and kind is IdKind.LINK and seq == "l2"


def test_parse_fragment_mark():
    base, kind, seq = parse_fragment("sess-abc#m1")
    assert base == "sess-abc" and kind is IdKind.MARK and seq == "m1"


def test_parse_fragment_falls_through_to_parse_id_for_card():
    base, kind, seq = parse_fragment("card_01jz8k2m")
    assert kind is IdKind.CARD and base == seq == "card_01jz8k2m"


def test_parse_fragment_bad_seq_raises():
    with pytest.raises(InvalidIdError):
        parse_fragment("card_01jz#x9")


def test_parse_card_still_works():
    kind, _ = parse_id("card_01jz8k2m")
    assert kind is IdKind.CARD


def test_parse_unknown_prefix_raises():
    with pytest.raises(InvalidIdError):
        parse_id("nope_123")
