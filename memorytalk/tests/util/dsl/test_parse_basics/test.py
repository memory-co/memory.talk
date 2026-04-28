"""util.dsl — basic parsing: empty input, single equality, AND chain, source field."""
from __future__ import annotations

from memory_talk_v2.util.dsl import parse


def test_parse_empty():
    assert parse("") == []
    assert parse("   ") == []


def test_parse_equal_string():
    preds = parse('source = "claude-code"')
    assert len(preds) == 1
    assert preds[0].field == "source"
    assert preds[0].op == "="
    assert preds[0].value == "claude-code"


def test_parse_and_chain():
    preds = parse('tag = "decision" AND source = "claude-code"')
    assert [p.field for p in preds] == ["tag", "source"]


def test_parse_source_field():
    preds = parse('source = "codex"')
    assert preds[0].field == "source"
