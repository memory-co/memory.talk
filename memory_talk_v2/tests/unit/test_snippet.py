from memory_talk_v2.service.snippet import extract_snippets


def test_empty_query_returns_empty():
    assert extract_snippets("hello world", "") == []


def test_highlights_match():
    snips = extract_snippets("LanceDB is zero-dependency", "LanceDB")
    assert snips
    assert "**LanceDB**" in snips[0]


def test_handles_chinese_via_jieba():
    text = "讨论 LanceDB 向量存储的选型理由"
    snips = extract_snippets(text, "LanceDB 选型")
    assert snips
    # At least one of the jieba tokens should be highlighted
    assert any("**" in s for s in snips)


def test_no_match_returns_empty():
    assert extract_snippets("hello world", "lambda") == []
