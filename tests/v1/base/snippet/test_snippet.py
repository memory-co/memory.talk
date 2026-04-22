"""Unit tests for extract_snippets."""
from __future__ import annotations

from memory_talk.service.snippet import extract_snippets


class TestSingleMatch:
    def test_basic_highlighting(self):
        out = extract_snippets("foo bar skills baz", "skills")
        assert out == ["foo bar **skills** baz"]

    def test_truncation_markers(self):
        text = ("x" * 100) + " skills " + ("y" * 100)
        [snippet] = extract_snippets(text, "skills", window=20)
        assert snippet.startswith("...")
        assert snippet.endswith("...")
        assert "**skills**" in snippet

    def test_no_prefix_ellipsis_at_start(self):
        [s] = extract_snippets("skills are important here " * 1, "skills", window=5)
        assert not s.startswith("...")

    def test_case_preserved_in_text_highlighted_case_insensitive(self):
        [s] = extract_snippets("the Skills Matter report", "skills")
        assert "**Skills**" in s


class TestMultipleMatches:
    def test_non_overlapping_ranges_produce_multi_segments(self):
        # put two distinct tokens far apart so their windows don't touch
        left = "context_a alpha " + ("x" * 200)
        right = ("y" * 200) + " beta context_b"
        text = left + right
        out = extract_snippets(text, "alpha beta", window=20)
        assert len(out) == 2
        assert any("**alpha**" in s for s in out)
        assert any("**beta**" in s for s in out)

    def test_overlapping_ranges_merge(self):
        # two tokens close together → windows overlap → 1 merged snippet
        text = "prefix alpha and beta suffix"
        out = extract_snippets(text, "alpha beta", window=40)
        assert len(out) == 1
        assert "**alpha**" in out[0] and "**beta**" in out[0]

    def test_max_segments_cap(self):
        # five distinct tokens far apart
        parts = [f"token{i}" + (" " * 200) for i in range(7)]
        text = "".join(parts)
        out = extract_snippets(
            text,
            "token0 token1 token2 token3 token4 token5 token6",
            max_segments=3,
            window=10,
        )
        assert len(out) == 3

    def test_same_token_twice_in_text_single_snippet(self):
        text = "hello skills and more skills here"
        out = extract_snippets(text, "skills", window=5)
        # Only one snippet (same token → one range; multiple occurrences of the
        # token inside that range get highlighted within the same snippet).
        assert len(out) == 1
        assert out[0].count("**skills**") >= 1


class TestQueryFiltering:
    def test_empty_query_returns_empty(self):
        assert extract_snippets("anything goes here", "") == []

    def test_whitespace_only_query(self):
        assert extract_snippets("anything", "   ") == []

    def test_short_tokens_dropped(self):
        # "a" and "I" are length 1 → dropped; "skills" remains
        out = extract_snippets("I found a skills reference", "a I skills")
        assert len(out) == 1
        assert "**skills**" in out[0]

    def test_all_short_tokens_returns_empty(self):
        assert extract_snippets("I am a person", "I a") == []

    def test_punctuation_only_token_dropped(self):
        # jieba.cut will often split "---" out; it has no word chars → dropped
        out = extract_snippets("hello skills world", "--- skills")
        assert len(out) == 1


class TestChinese:
    def test_chinese_token(self):
        text = "今天我们讨论了数据库选型的问题"
        [s] = extract_snippets(text, "数据库", window=5)
        assert "**数据库**" in s

    def test_mixed_chinese_and_english(self):
        text = "项目决定用 LanceDB 做向量存储"
        out = extract_snippets(text, "LanceDB 向量", window=50)
        # Both tokens hit; their windows likely overlap → 1 snippet highlighting both
        assert len(out) == 1
        assert "**LanceDB**" in out[0]
        assert "**向量**" in out[0]


class TestWindowBound:
    def test_window_size_caps_output_length(self):
        text = "x" * 500 + " target " + "y" * 500
        [s] = extract_snippets(text, "target", window=10)
        # snippet body ≤ len("target") + 2*window + optional "..." prefixes
        # 2 tokens highlighting adds ** ** (4 chars)
        assert len(s) <= len("target") + 2 * 10 + 4 + len("......")
