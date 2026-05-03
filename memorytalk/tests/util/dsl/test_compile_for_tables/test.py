"""util.dsl — compile_for() emits SQL fragments and enforces per-table field whitelists."""
from __future__ import annotations

from memorytalk.util.dsl import compile_for, parse


def test_compile_for_sessions_with_source():
    preds = parse('source = "claude-code" AND tag = "decision"')
    result = compile_for(preds, "sessions")
    assert result is not None
    sql, params = result
    assert "sessions.source = ?" in sql
    # tag now joins the standalone `tags` table by key
    assert "FROM tags" in sql
    assert "tags.subject_id = sessions.session_id" in sql
    assert "tags.key = ?" in sql
    assert params == ["claude-code", "decision"]


def test_compile_for_cards_rejects_sessions_only_field():
    preds = parse('source = "claude-code"')
    # source is sessions-only; compile for cards returns None
    assert compile_for(preds, "cards") is None


def test_compile_for_sessions_rejects_cards_only_field():
    preds = parse('card_id = "card_x"')
    assert compile_for(preds, "sessions") is None


def test_compile_for_cards_with_tag():
    """tag is now allowed on cards too — joins the same tags table."""
    preds = parse('tag = "topic"')
    result = compile_for(preds, "cards")
    assert result is not None
    sql, params = result
    assert "FROM tags" in sql
    assert "tags.subject_id = cards.card_id" in sql
    assert params == ["topic"]
