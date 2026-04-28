"""util.snippet — Chinese query routes through jieba tokenization."""
from __future__ import annotations

from memorytalk.util.snippet import extract_snippets


def test_handles_chinese_via_jieba():
    text = "讨论 LanceDB 向量存储的选型理由"
    snips = extract_snippets(text, "LanceDB 选型")
    assert snips
    # At least one of the jieba tokens should be highlighted
    assert any("**" in s for s in snips)
