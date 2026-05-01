"""Unit tests for ``_resolve_auth_key`` — the env-var renderer used to
turn the ``${VAR}`` form into the actual API key at request time.
"""
from __future__ import annotations
import pytest

from memorytalk.provider.embedding import _resolve_auth_key


def test_literal_passes_through_unchanged():
    assert _resolve_auth_key("sk-abcdef-1234567890") == "sk-abcdef-1234567890"


def test_dollar_sign_must_be_doubled_to_be_literal():
    # string.Template treats $$ as a literal $
    assert _resolve_auth_key("price-$$-tier") == "price-$-tier"


def test_brace_form_expands_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_KEY_TEST_X", "secret-1")
    assert _resolve_auth_key("${AUTH_KEY_TEST_X}") == "secret-1"


def test_bare_form_expands_from_env(monkeypatch):
    """Template also accepts $NAME (no braces) — same expansion path."""
    monkeypatch.setenv("AUTH_KEY_TEST_Y", "secret-2")
    assert _resolve_auth_key("$AUTH_KEY_TEST_Y") == "secret-2"


def test_missing_env_raises_keyerror(monkeypatch):
    monkeypatch.delenv("AUTH_KEY_TEST_MISSING", raising=False)
    with pytest.raises(KeyError, match="AUTH_KEY_TEST_MISSING"):
        _resolve_auth_key("${AUTH_KEY_TEST_MISSING}")


def test_empty_string_returns_empty():
    assert _resolve_auth_key("") == ""


def test_mixed_literal_and_env_substitutes(monkeypatch):
    """When a literal contains both text and ${VAR} the var IS still expanded.
    This is Template's documented behavior; we don't try to suppress it because
    a real auth key has no good reason to look like 'prefix${VAR}suffix'."""
    monkeypatch.setenv("AUTH_KEY_TEST_Z", "MID")
    assert _resolve_auth_key("pre-${AUTH_KEY_TEST_Z}-post") == "pre-MID-post"
