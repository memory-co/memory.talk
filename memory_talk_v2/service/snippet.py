"""Markdown-highlighted match snippets for /v2/search hits.

Ported from v1: jieba-tokenize the query, regex-highlight in source text.
Does not use any FTS engine's built-in snippet() — keeps output fully
controllable and identical across cards / sessions.
"""
from __future__ import annotations
import re


_MIN_TOKEN_LEN = 2


def _query_tokens(query: str) -> list[str]:
    import jieba

    out: list[str] = []
    seen: set[str] = set()
    for tok in jieba.cut(query or ""):
        t = tok.strip()
        if len(t) < _MIN_TOKEN_LEN:
            continue
        if not re.search(r"\w", t, flags=re.UNICODE):
            continue
        low = t.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(t)
    return out


def _highlight(text: str, tokens: list[str]) -> str:
    if not tokens:
        return text
    ordered = sorted(set(tokens), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(t) for t in ordered), flags=re.IGNORECASE)
    return pattern.sub(lambda m: f"**{m.group(0)}**", text)


def extract_snippets(
    text: str,
    query: str,
    *,
    max_segments: int = 5,
    window: int = 40,
) -> list[str]:
    """Up to max_segments markdown-highlighted snippets, centered on first
    occurrences of each query token. Overlapping ranges are merged."""
    if not text or not query.strip():
        return []
    tokens = _query_tokens(query)
    if not tokens:
        return []
    lower = text.lower()
    ranges: list[tuple[int, int]] = []
    for tok in tokens:
        idx = lower.find(tok.lower())
        if idx < 0:
            continue
        start = max(0, idx - window)
        end = min(len(text), idx + len(tok) + window)
        ranges.append((start, end))
    if not ranges:
        return []
    ranges.sort()
    merged: list[list[int]] = [list(ranges[0])]
    for s, e in ranges[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out: list[str] = []
    for s, e in merged[:max_segments]:
        chunk = text[s:e]
        chunk = _highlight(chunk, tokens)
        if s > 0:
            chunk = "..." + chunk
        if e < len(text):
            chunk = chunk + "..."
        out.append(chunk)
    return out
