"""util.dsl — LIKE / NOT LIKE / IN / NOT IN operators."""
from __future__ import annotations

from memory_talk_v2.util.dsl import parse


def test_parse_like_and_not_like():
    preds = parse('tag LIKE "proj%" AND tag NOT LIKE "old%"')
    assert preds[0].op == "LIKE"
    assert preds[1].op == "NOTLIKE"


def test_parse_in_and_not_in():
    preds = parse('source IN ("claude-code", "codex") AND tag NOT IN ("draft")')
    assert preds[0].op == "IN" and preds[0].value == ["claude-code", "codex"]
    assert preds[1].op == "NOTIN" and preds[1].value == ["draft"]
