"""util.dsl — parse() rejects malformed input with DSLError."""
from __future__ import annotations

import pytest

from memorytalk.util.dsl import DSLError, parse


def test_parse_truncated_predicate():
    with pytest.raises(DSLError):
        parse("tag = ")


def test_parse_unknown_field():
    with pytest.raises(DSLError):
        parse('unknown = "x"')


def test_parse_in_without_list():
    with pytest.raises(DSLError):
        parse('tag IN "x"')
