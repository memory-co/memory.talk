"""DSL parser and SQLite compiler tests."""
from __future__ import annotations
from datetime import datetime

import pytest

from memory_talk.dsl import (
    DSLError,
    build_cards_where,
    build_sessions_where,
    parse,
)


FIXED_NOW = datetime(2026, 4, 19, 12, 0, 0)


# ---------- parser ----------


class TestParser:
    def test_empty(self):
        assert parse("") == []

    def test_simple_equality(self):
        [p] = parse('session_id = "abc"')
        assert p.field == "session_id" and p.op == "=" and p.value == "abc"

    def test_implicit_and(self):
        preds = parse('session_id = "abc" tag = "x"')
        assert len(preds) == 2
        assert [p.field for p in preds] == ["session_id", "tag"]

    def test_explicit_and(self):
        preds = parse('session_id = "abc" AND tag = "x"')
        assert len(preds) == 2

    def test_compare_ops(self):
        for op in ("=", "!=", ">", ">=", "<", "<="):
            [p] = parse(f'created_at {op} "2026-01-01"')
            assert p.op == op

    def test_like(self):
        [p] = parse('tag LIKE "project:%"')
        assert p.op == "LIKE" and p.value == "project:%"

    def test_not_like(self):
        [p] = parse('tag NOT LIKE "skip-%"')
        assert p.op == "NOTLIKE"

    def test_in(self):
        [p] = parse('tag IN ("a", "b", "c")')
        assert p.op == "IN" and p.value == ["a", "b", "c"]

    def test_not_in(self):
        [p] = parse('session_id NOT IN ("s1", "s2")')
        assert p.op == "NOTIN" and p.value == ["s1", "s2"]

    def test_relative_time_value(self):
        [p] = parse("created_at >= -7d")
        assert p.op == ">=" and p.value == "-7d"

    def test_escaped_string(self):
        [p] = parse('session_id = "a\\"b"')
        assert p.value == 'a"b'

    def test_unknown_field_raises(self):
        with pytest.raises(DSLError, match="unknown field"):
            parse('summary LIKE "%x%"')

    def test_unterminated_string(self):
        with pytest.raises(DSLError, match="unterminated"):
            parse('session_id = "abc')

    def test_malformed_reltime(self):
        with pytest.raises(DSLError, match="relative time"):
            parse("created_at >= -7x")

    def test_missing_op(self):
        with pytest.raises(DSLError):
            parse("session_id")


# ---------- cards compiler ----------


class TestCardsWhere:
    def test_empty(self):
        sql, params = build_cards_where([], now=FIXED_NOW)
        assert sql == "" and params == []

    def test_session_equality(self):
        sql, params = build_cards_where(parse('session_id = "abc"'), now=FIXED_NOW)
        assert sql == "c.session_id = ?"
        assert params == ["abc"]

    def test_card_id(self):
        sql, params = build_cards_where(parse('card_id = "01j"'), now=FIXED_NOW)
        assert sql == "c.card_id = ?"
        assert params == ["01j"]

    def test_created_at_iso(self):
        sql, params = build_cards_where(parse('created_at >= "2026-04-01"'), now=FIXED_NOW)
        assert sql == "c.created_at >= ?"
        assert params == ["2026-04-01"]

    def test_created_at_relative(self):
        sql, params = build_cards_where(parse("created_at >= -7d"), now=FIXED_NOW)
        assert sql == "c.created_at >= ?"
        # 7 days before FIXED_NOW
        assert params == [datetime(2026, 4, 12, 12, 0, 0).isoformat()]

    def test_tag_equality(self):
        sql, params = build_cards_where(parse('tag = "decision"'), now=FIXED_NOW)
        assert "EXISTS (SELECT 1 FROM json_each(s.tags) WHERE value = ?)" in sql
        assert params == ["decision"]

    def test_tag_not_equal_is_not_exists(self):
        sql, params = build_cards_where(parse('tag != "x"'), now=FIXED_NOW)
        assert "NOT EXISTS" in sql
        assert params == ["x"]

    def test_tag_like(self):
        sql, params = build_cards_where(parse('tag LIKE "project:%"'), now=FIXED_NOW)
        assert "EXISTS" in sql and "value LIKE ?" in sql
        assert params == ["project:%"]

    def test_tag_not_like(self):
        sql, params = build_cards_where(parse('tag NOT LIKE "draft-%"'), now=FIXED_NOW)
        assert "NOT EXISTS" in sql and "value LIKE ?" in sql
        assert params == ["draft-%"]

    def test_tag_in(self):
        sql, params = build_cards_where(parse('tag IN ("a", "b")'), now=FIXED_NOW)
        assert "value IN (?, ?)" in sql
        assert params == ["a", "b"]

    def test_tag_not_in(self):
        sql, params = build_cards_where(parse('tag NOT IN ("a", "b")'), now=FIXED_NOW)
        assert "NOT EXISTS" in sql and "value IN (?, ?)" in sql
        assert params == ["a", "b"]

    def test_and_composition(self):
        sql, params = build_cards_where(
            parse('session_id = "abc" AND created_at >= -1d AND tag = "x"'),
            now=FIXED_NOW,
        )
        assert " AND " in sql
        assert sql.count("?") == 3
        assert len(params) == 3


# ---------- sessions compiler ----------


class TestSessionsWhere:
    def test_empty_returns_empty_tuple(self):
        assert build_sessions_where([], now=FIXED_NOW) == ("", [])

    def test_card_id_downgrades_to_none(self):
        result = build_sessions_where(parse('card_id = "x"'), now=FIXED_NOW)
        assert result is None

    def test_card_id_mixed_still_none(self):
        """Any card_id predicate → the whole sessions side drops."""
        result = build_sessions_where(
            parse('session_id = "abc" AND card_id = "x"'), now=FIXED_NOW
        )
        assert result is None

    def test_session_id_on_sessions_table(self):
        sql, params = build_sessions_where(parse('session_id = "abc"'), now=FIXED_NOW)
        assert sql == "s.session_id = ?"
        assert params == ["abc"]

    def test_tag_uses_sessions_table(self):
        sql, params = build_sessions_where(parse('tag = "decision"'), now=FIXED_NOW)
        assert "json_each(s.tags)" in sql
        assert params == ["decision"]

    def test_created_at_on_sessions(self):
        sql, params = build_sessions_where(parse('created_at < "2026-05-01"'), now=FIXED_NOW)
        assert sql == "s.created_at < ?"
        assert params == ["2026-05-01"]


# ---------- parameterization safety ----------


class TestInjectionSafety:
    def test_values_do_not_leak_into_sql(self):
        """Injected SQL in a string literal must stay as a bound parameter."""
        # payload avoids embedded double quote; `'` and `;` exercise the tokenizer
        malicious = "abc'); DROP TABLE cards; --"
        sql, params = build_cards_where(
            parse(f'session_id = "{malicious}"'), now=FIXED_NOW
        )
        assert "DROP TABLE" not in sql
        assert params == [malicious]
