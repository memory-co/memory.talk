"""Unit tests for util/dsl.py — the search WHERE-clause parser."""
from __future__ import annotations
import pytest

from memorytalk.util.dsl import DSLError, Predicate, parse


class TestParseBasics:
    def test_empty_string_returns_empty_filter(self):
        f = parse("")
        assert f.empty()
        assert f.predicates == []

    def test_simple_equality(self):
        f = parse('source = "claude-code"')
        assert len(f.predicates) == 1
        p = f.predicates[0]
        assert p.field == "source"
        assert p.op == "="
        assert p.value == "claude-code"

    def test_number_value(self):
        f = parse("review_count = 0")
        assert f.predicates[0].value == 0

    def test_all_numeric_ops(self):
        for op in ["=", "!=", "<", ">", "<=", ">="]:
            f = parse(f"review_up {op} 3")
            assert f.predicates[0].op == op

    def test_like(self):
        f = parse('card_id LIKE "card_%"')
        assert f.predicates[0].op == "LIKE"
        assert f.predicates[0].value == "card_%"

    def test_in_list(self):
        f = parse('source IN ("claude-code", "codex")')
        p = f.predicates[0]
        assert p.op == "IN"
        assert p.value == ["claude-code", "codex"]

    def test_not_in_list(self):
        f = parse('source NOT IN ("claude-code")')
        assert f.predicates[0].op == "NOT_IN"

    def test_and_combines_predicates(self):
        f = parse('review_count = 0 AND read_count > 10')
        assert len(f.predicates) == 2


class TestParseErrors:
    def test_unknown_field(self):
        with pytest.raises(DSLError, match="unknown field"):
            parse("foo = 1")

    def test_unexpected_token(self):
        with pytest.raises(DSLError):
            parse("review_up")

    def test_missing_value(self):
        with pytest.raises(DSLError):
            parse("review_up =")

    def test_missing_connector(self):
        # Two predicates without AND.
        with pytest.raises(DSLError):
            parse('source = "x" source = "y"')

    def test_or_not_supported(self):
        with pytest.raises(DSLError):
            parse('source = "x" OR source = "y"')

    def test_empty_in_list(self):
        with pytest.raises(DSLError):
            parse("source IN ()")

    def test_unbalanced_paren(self):
        with pytest.raises(DSLError):
            parse('source IN ("x"')


class TestFieldDomainScoping:
    """Field-applicability rules: a predicate on a card-only field makes
    sessions vacuously fail, and vice-versa — see docs/cli/v4/search.md
    "字段应用域规则"."""

    def test_card_only_field_excludes_sessions(self):
        f = parse("review_count = 0")
        assert f.scope_includes("card")
        assert not f.scope_includes("session")

    def test_session_only_field_excludes_cards(self):
        f = parse('source = "claude-code"')
        assert not f.scope_includes("card")
        assert f.scope_includes("session")

    def test_shared_field_includes_both(self):
        f = parse('created_at > "2026-01-01"')
        assert f.scope_includes("card")
        assert f.scope_includes("session")

    def test_explicit_type_field(self):
        # `type` is universal — applies to both, but evaluate() narrows.
        f = parse('type = "card"')
        assert f.scope_includes("card")
        assert f.scope_includes("session")


class TestEvaluate:
    def test_eq_string(self):
        p = Predicate(field="source", op="=", value="claude-code")
        assert p.evaluate({"source": "claude-code"}, kind="session")
        assert not p.evaluate({"source": "codex"}, kind="session")

    def test_lt_numeric(self):
        p = Predicate(field="review_count", op="<", value=5)
        assert p.evaluate({"review_count": 3}, kind="card")
        assert not p.evaluate({"review_count": 5}, kind="card")

    def test_like_case_insensitive(self):
        p = Predicate(field="card_id", op="LIKE", value="CARD_%")
        assert p.evaluate({"card_id": "card_01abc"}, kind="card")

    def test_in_list(self):
        p = Predicate(field="source", op="IN", value=["claude-code", "codex"])
        assert p.evaluate({"source": "codex"}, kind="session")
        assert not p.evaluate({"source": "other"}, kind="session")

    def test_type_field_via_kind(self):
        p = Predicate(field="type", op="=", value="card")
        assert p.evaluate({}, kind="card")
        assert not p.evaluate({}, kind="session")

    def test_card_only_field_on_session_candidate_fails(self):
        # `session` candidates don't carry review_count → vacuously false.
        p = Predicate(field="review_count", op="=", value=0)
        assert not p.evaluate({}, kind="session")

    def test_session_only_field_on_card_candidate_fails(self):
        p = Predicate(field="source", op="=", value="claude-code")
        assert not p.evaluate({"source": "claude-code"}, kind="card")
