import pytest
from datetime import datetime, timezone

from memory_talk_v2.dsl import parse, compile_for, DSLError


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


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


def test_parse_like_and_not_like():
    preds = parse('tag LIKE "proj%" AND tag NOT LIKE "old%"')
    assert preds[0].op == "LIKE"
    assert preds[1].op == "NOTLIKE"


def test_parse_in_and_not_in():
    preds = parse('source IN ("claude-code", "codex") AND tag NOT IN ("draft")')
    assert preds[0].op == "IN" and preds[0].value == ["claude-code", "codex"]
    assert preds[1].op == "NOTIN" and preds[1].value == ["draft"]


def test_parse_reltime():
    preds = parse('created_at > -7d', now=NOW)
    assert preds[0].field == "created_at"
    assert preds[0].value.startswith("2026-04-15")  # 7 days before NOW


def test_parse_source_field_is_new():
    preds = parse('source = "codex"')
    assert preds[0].field == "source"


def test_compile_for_sessions_with_source():
    preds = parse('source = "claude-code" AND tag = "decision"')
    result = compile_for(preds, "sessions")
    assert result is not None
    sql, params = result
    assert "sessions.source = ?" in sql
    assert "json_each(sessions.tags)" in sql
    assert params == ["claude-code", "decision"]


def test_compile_for_cards_rejects_sessions_only_field():
    preds = parse('source = "claude-code"')
    # source is sessions-only; compile for cards returns None
    assert compile_for(preds, "cards") is None


def test_compile_for_sessions_rejects_cards_only_field():
    preds = parse('card_id = "card_x"')
    assert compile_for(preds, "sessions") is None


def test_parse_errors():
    with pytest.raises(DSLError):
        parse('tag = ')
    with pytest.raises(DSLError):
        parse('unknown = "x"')
    with pytest.raises(DSLError):
        parse('tag IN "x"')
