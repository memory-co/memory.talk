"""Unit tests for util/highlight.py — keyword-wrap + truncate + snippet.

Also covers ``memorytalk.cli._format._fmt_time`` (lives outside this module
but pairs nicely with the other small renderer helpers tested here)."""
from __future__ import annotations
import datetime as _dt

import pytest

from memorytalk.cli._format import _fmt_time
from memorytalk.util.highlight import highlight_keywords, make_snippet, truncate


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


class TestMakeSnippet:
    def test_short_text_returns_whole_with_highlight(self):
        # Text fits the budget — pass through, highlight any matches.
        out = make_snippet("LanceDB is fast", "LanceDB", head_chars=100)
        assert out == "**LanceDB** is fast"

    def test_empty_text(self):
        assert make_snippet("", "LanceDB", head_chars=100) == ""

    def test_keyword_window_centers_on_first_match(self):
        # Long text with the keyword in the middle — window around the
        # match with … on both sides.
        text = "x" * 200 + "LanceDB" + "y" * 200
        out = make_snippet(text, "LanceDB", head_chars=50)
        assert out.startswith("…")
        assert out.endswith("…")
        assert "**LanceDB**" in out
        # Strip the ** markers + ellipses; what's left is the actual text
        # window and must honor the head_chars budget.
        plain = out.replace("**", "").strip("…")
        assert len(plain) == 50

    def test_keyword_window_near_start_no_leading_ellipsis(self):
        text = "LanceDB " + "y" * 200
        out = make_snippet(text, "LanceDB", head_chars=50)
        assert not out.startswith("…")
        assert out.endswith("…")
        assert "**LanceDB**" in out

    def test_keyword_window_near_end_no_trailing_ellipsis(self):
        text = "x" * 200 + " LanceDB"
        out = make_snippet(text, "LanceDB", head_chars=50)
        assert out.startswith("…")
        assert not out.endswith("…")
        assert "**LanceDB**" in out

    def test_vector_only_hit_returns_head_no_highlight(self):
        # No query token in text — head preview with trailing ….
        text = "完全不相关的语义近邻" + "x" * 200
        out = make_snippet(text, "LanceDB", head_chars=20)
        assert out.endswith("…")
        assert "**" not in out
        # 20 chars of head + 1 ellipsis
        assert len(out) == 21

    def test_vector_only_hit_short_text_no_ellipsis(self):
        # Text shorter than budget, no match → whole text, no highlight,
        # no ellipsis.
        out = make_snippet("纯语义相关的短句", "LanceDB", head_chars=100)
        assert out == "纯语义相关的短句"

    def test_empty_query_falls_back_to_head_preview(self):
        text = "x" * 200
        out = make_snippet(text, "", head_chars=50)
        assert out == "x" * 50 + "…"

    def test_chinese_keyword_window(self):
        text = "前面一些铺垫" * 20 + "选 LanceDB 做向量存储" + "后面一些总结" * 20
        out = make_snippet(text, "LanceDB 向量", head_chars=40)
        # The earliest match (LanceDB) anchors the window; "向量" may also
        # land inside and gets highlighted too.
        assert "**LanceDB**" in out
        assert out.startswith("…") and out.endswith("…")


def _ago(seconds: int) -> str:
    t = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=seconds)
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


class TestFmtTime:
    def test_empty_input(self):
        assert _fmt_time(None) == ""
        assert _fmt_time("") == ""

    def test_unparseable_input(self):
        assert _fmt_time("not-a-timestamp") == ""

    def test_just_now(self):
        assert _fmt_time(_ago(30)).endswith("(just now)")

    def test_minutes_plural(self):
        assert _fmt_time(_ago(60)).endswith("(1 minute ago)")
        assert _fmt_time(_ago(180)).endswith("(3 minutes ago)")

    def test_hours_plural(self):
        assert _fmt_time(_ago(3700)).endswith("(1 hour ago)")
        assert _fmt_time(_ago(7300)).endswith("(2 hours ago)")

    def test_days_plural(self):
        assert _fmt_time(_ago(86400)).endswith("(1 day ago)")
        assert _fmt_time(_ago(86400 * 5)).endswith("(5 days ago)")

    def test_months(self):
        # 45 days → 1 month (rolls over at 30-day boundary)
        assert _fmt_time(_ago(86400 * 45)).endswith("(1 month ago)")
        assert _fmt_time(_ago(86400 * 90)).endswith("(3 months ago)")

    def test_years(self):
        assert _fmt_time(_ago(86400 * 400)).endswith("(1 year ago)")
        assert _fmt_time(_ago(86400 * 800)).endswith("(2 years ago)")

    def test_absolute_portion_format(self):
        out = _fmt_time(_ago(120))
        # Absolute portion should look like YYYY-MM-DD HH:MM at the start.
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} \(", out)

    def test_handles_naive_iso_as_utc(self):
        # No tzinfo in input → assume UTC, don't crash.
        t = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=120)
        naive = t.replace(tzinfo=None).isoformat(timespec="seconds")
        out = _fmt_time(naive)
        assert "ago" in out
