"""util.snippet — extract_snippets() english path: empty query, hit, miss."""
from __future__ import annotations

from memorytalk.util.snippet import extract_snippets


def test_empty_query_returns_empty():
    assert extract_snippets("hello world", "") == []


def test_highlights_match():
    snips = extract_snippets("LanceDB is zero-dependency", "LanceDB")
    assert snips
    assert "**LanceDB**" in snips[0]


def test_no_match_returns_empty():
    assert extract_snippets("hello world", "lambda") == []
