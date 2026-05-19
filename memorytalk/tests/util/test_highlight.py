"""Unit tests for util/highlight.py — keyword-wrap + truncate."""
from __future__ import annotations
import pytest

from memorytalk.util.highlight import highlight_keywords, truncate


class TestHighlight:
    def test_basic_wrap(self):
        out = highlight_keywords("LanceDB is fast", "LanceDB")
        assert out == "**LanceDB** is fast"

    def test_multiple_occurrences(self):
        out = highlight_keywords("LanceDB beats LanceDB clones", "LanceDB")
        assert out == "**LanceDB** beats **LanceDB** clones"

    def test_case_insensitive_but_preserves_case_in_output(self):
        out = highlight_keywords("lancedb is fast", "LanceDB")
        assert "**lancedb**" in out

    def test_empty_text(self):
        assert highlight_keywords("", "LanceDB") == ""

    def test_empty_query(self):
        assert highlight_keywords("LanceDB is fast", "") == "LanceDB is fast"

    def test_no_match(self):
        out = highlight_keywords("nothing matches here", "LanceDB")
        assert out == "nothing matches here"

    def test_longer_token_consumed_first(self):
        # "LanceDB" should consume the full word before "Lance" or "DB"
        # would (regex alternation matches the longest registered token first
        # because we sort by length desc).
        out = highlight_keywords("LanceDB rocks", "Lance LanceDB")
        # Either order is acceptable so long as the full word got wrapped.
        assert "**LanceDB**" in out
        # Confirm we don't get nested **L**ance**DB** by virtue of the
        # single-regex-pass guarantee.
        assert "***" not in out

    def test_no_double_wrap_with_overlapping_terms(self):
        # Even with overlapping query tokens, the single-pass regex
        # guarantees each position is wrapped at most once.
        out = highlight_keywords("LanceDB", "LanceDB Lance DB")
        assert out.count("**") == 2  # one open + one close

    def test_single_ascii_char_not_highlighted(self):
        # Tokenizer drops single-char ASCII tokens to avoid wrapping every
        # 'a' in a paragraph.
        out = highlight_keywords("a quick brown fox", "a")
        assert out == "a quick brown fox"

    def test_chinese_tokens(self):
        # jieba splits Chinese phrases; multi-char CJK tokens are kept.
        out = highlight_keywords("我选 LanceDB 做向量存储", "LanceDB 向量")
        assert "**LanceDB**" in out
        assert "**向量**" in out

    def test_punctuation_only_query_no_match(self):
        out = highlight_keywords("hello world", " . , ")
        assert out == "hello world"


class TestTruncate:
    def test_short_text_passthrough(self):
        assert truncate("short", limit=200) == "short"

    def test_long_text_truncated_with_ellipsis(self):
        text = "x" * 250
        out = truncate(text, limit=200)
        assert out.endswith("…")
        assert len(out) == 201  # 200 + 1-char ellipsis

    def test_exact_limit_passthrough(self):
        text = "x" * 200
        assert truncate(text, limit=200) == text

    def test_empty(self):
        assert truncate("", limit=200) == ""
        assert truncate(None, limit=200) == ""  # type: ignore
