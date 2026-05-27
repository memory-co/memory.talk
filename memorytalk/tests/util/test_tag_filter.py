"""Unit tests for util/tag_filter: parser shape + SQL output.

The integration coverage (does the SQL actually filter the right
rows?) lives in tests/api/test_sessions_list.py — here we pin
contract: each surface form parses into the right TagPredicate, and
each TagPredicate translates to the right SQL fragment.
"""
from __future__ import annotations
import pytest

from memorytalk.util.tag_filter import TagPredicate, parse_tag_arg, to_sql
from memorytalk.util.tags import TagValidationError


# ────────── parse_tag_arg: each form ──────────

def test_eq_form():
    p = parse_tag_arg("project=billing")
    assert p == TagPredicate(key="project", op="eq", values=["billing"])


def test_ne_form():
    p = parse_tag_arg("status!=draft")
    assert p == TagPredicate(key="status", op="ne", values=["draft"])


def test_in_form_two_values():
    p = parse_tag_arg("status=wip,review")
    assert p == TagPredicate(key="status", op="in", values=["wip", "review"])


def test_in_form_three_values():
    p = parse_tag_arg("priority=P0,P1,P2")
    assert p.op == "in"
    assert p.values == ["P0", "P1", "P2"]


def test_present_form():
    p = parse_tag_arg("project")
    assert p == TagPredicate(key="project", op="present", values=[])


def test_absent_form():
    p = parse_tag_arg("!project")
    assert p == TagPredicate(key="project", op="absent", values=[])


# ────────── parse_tag_arg: edge cases + rejection ──────────

def test_strips_whitespace():
    assert parse_tag_arg("  project=billing  ").key == "project"


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_rejected(bad):
    with pytest.raises(TagValidationError):
        parse_tag_arg(bad)


def test_bang_only_rejected():
    with pytest.raises(TagValidationError):
        parse_tag_arg("!")


def test_eq_missing_value_rejected():
    with pytest.raises(TagValidationError):
        parse_tag_arg("project=")


def test_ne_missing_value_rejected():
    with pytest.raises(TagValidationError):
        parse_tag_arg("project!=")


def test_eq_missing_key_rejected():
    with pytest.raises(TagValidationError):
        parse_tag_arg("=billing")


def test_in_empty_member_rejected():
    """``K=a,,b`` is almost certainly a typo; reject loudly rather than
    silently treating it as ``K IN (a, "", b)``."""
    with pytest.raises(TagValidationError):
        parse_tag_arg("status=a,,b")


def test_invalid_key_rejected():
    """Key regex (leading digit) — reuses validate_key from util/tags."""
    with pytest.raises(TagValidationError):
        parse_tag_arg("1bad=x")


def test_bang_check_takes_priority_over_ne():
    """``!foo`` is absent, not ``! foo` something. Order of checks matters."""
    p = parse_tag_arg("!foo")
    assert p.op == "absent"
    assert p.key == "foo"


# ────────── to_sql: each form ──────────

def test_sql_eq():
    clauses, params = to_sql([
        TagPredicate(key="project", op="eq", values=["billing"]),
    ])
    assert clauses == ["json_extract(tags, ?) = ?"]
    assert params == ["$.project", "billing"]


def test_sql_ne():
    clauses, params = to_sql([
        TagPredicate(key="status", op="ne", values=["draft"]),
    ])
    assert clauses == ["json_extract(tags, ?) != ?"]
    assert params == ["$.status", "draft"]


def test_sql_in():
    clauses, params = to_sql([
        TagPredicate(key="status", op="in", values=["wip", "review", "blocked"]),
    ])
    assert clauses == ["json_extract(tags, ?) IN (?, ?, ?)"]
    assert params == ["$.status", "wip", "review", "blocked"]


def test_sql_present():
    clauses, params = to_sql([
        TagPredicate(key="project", op="present", values=[]),
    ])
    assert clauses == ["json_extract(tags, ?) IS NOT NULL"]
    assert params == ["$.project"]


def test_sql_absent():
    clauses, params = to_sql([
        TagPredicate(key="project", op="absent", values=[]),
    ])
    assert clauses == ["json_extract(tags, ?) IS NULL"]
    assert params == ["$.project"]


def test_sql_column_override():
    """Used by card list (also ``tags`` column today but the option
    exists so future tables don't have to touch this code)."""
    clauses, params = to_sql(
        [TagPredicate(key="x", op="eq", values=["y"])],
        column="card_tags",
    )
    assert clauses == ["json_extract(card_tags, ?) = ?"]


def test_sql_multiple_predicates_param_order():
    """Per-clause param ordering matters — bind sequence must align
    with the WHERE assembly."""
    clauses, params = to_sql([
        TagPredicate(key="project", op="eq", values=["billing"]),
        TagPredicate(key="status",  op="in", values=["wip", "review"]),
        TagPredicate(key="draft",   op="absent", values=[]),
    ])
    assert clauses == [
        "json_extract(tags, ?) = ?",
        "json_extract(tags, ?) IN (?, ?)",
        "json_extract(tags, ?) IS NULL",
    ]
    assert params == [
        "$.project", "billing",
        "$.status", "wip", "review",
        "$.draft",
    ]


def test_sql_empty_predicates():
    clauses, params = to_sql([])
    assert clauses == []
    assert params == []
