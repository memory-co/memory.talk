"""Unit tests for ``render_env_template`` — generic ${VAR} env-var
expansion utility used by the embedding provider (and any future
config field that opts in)."""
from __future__ import annotations
import pytest

from memorytalk.util.env_template import render_env_template, render_env_in_obj


def test_literal_passes_through_unchanged():
    assert render_env_template("sk-abcdef-1234567890") == "sk-abcdef-1234567890"


def test_dollar_sign_must_be_doubled_to_be_literal():
    # string.Template treats $$ as a literal $
    assert render_env_template("price-$$-tier") == "price-$-tier"


def test_brace_form_expands_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_KEY_TEST_X", "secret-1")
    assert render_env_template("${AUTH_KEY_TEST_X}") == "secret-1"


def test_bare_form_expands_from_env(monkeypatch):
    """Template also accepts $NAME (no braces) — same expansion path."""
    monkeypatch.setenv("AUTH_KEY_TEST_Y", "secret-2")
    assert render_env_template("$AUTH_KEY_TEST_Y") == "secret-2"


def test_missing_env_raises_keyerror(monkeypatch):
    monkeypatch.delenv("AUTH_KEY_TEST_MISSING", raising=False)
    with pytest.raises(KeyError, match="AUTH_KEY_TEST_MISSING"):
        render_env_template("${AUTH_KEY_TEST_MISSING}")


def test_empty_string_returns_empty():
    assert render_env_template("") == ""


def test_mixed_literal_and_env_substitutes(monkeypatch):
    """When a literal contains both text and ${VAR} the var IS still expanded.
    This is Template's documented behavior; we don't try to suppress it because
    a real auth key has no good reason to look like 'prefix${VAR}suffix'."""
    monkeypatch.setenv("AUTH_KEY_TEST_Z", "MID")
    assert render_env_template("pre-${AUTH_KEY_TEST_Z}-post") == "pre-MID-post"


# ---------- render_env_in_obj ----------

def test_walker_renders_nested_dict_strings(monkeypatch):
    monkeypatch.setenv("WALK_TEST_A", "AA")
    monkeypatch.setenv("WALK_TEST_B", "BB")
    obj = {
        "top": "${WALK_TEST_A}",
        "nested": {"inner": "${WALK_TEST_B}", "literal": "plain"},
    }
    render_env_in_obj(obj)
    assert obj == {
        "top": "AA",
        "nested": {"inner": "BB", "literal": "plain"},
    }


def test_walker_renders_strings_in_lists(monkeypatch):
    monkeypatch.setenv("WALK_TEST_C", "CC")
    obj = {"list": ["${WALK_TEST_C}", "literal", {"deep": "${WALK_TEST_C}"}]}
    render_env_in_obj(obj)
    assert obj == {"list": ["CC", "literal", {"deep": "CC"}]}


def test_walker_passes_through_non_string_leaves():
    obj = {"a": 1, "b": 1.5, "c": True, "d": None, "e": [1, 2]}
    render_env_in_obj(obj)
    assert obj == {"a": 1, "b": 1.5, "c": True, "d": None, "e": [1, 2]}


def test_walker_missing_var_raises_keyerror(monkeypatch):
    monkeypatch.delenv("WALK_TEST_MISSING", raising=False)
    obj = {"x": "${WALK_TEST_MISSING}"}
    with pytest.raises(KeyError, match="WALK_TEST_MISSING"):
        render_env_in_obj(obj)
