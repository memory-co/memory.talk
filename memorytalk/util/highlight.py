"""Wrap query keywords with ``**…**`` for inline highlighting.

Used by the search service to produce display-ready ``text`` /
``insight`` strings that have the matched portions emphasized. Tokens
are pulled via jieba so Chinese phrases tokenize the same way both the
FTS index and the highlighter see them — match boundaries stay aligned.

Single pass per text. Already-bolded content isn't double-wrapped
because we use one combined regex (the OR-of-tokens) and a single
``re.sub`` call: each character is visited once, so no re-entry into
previously-replaced spans.
"""
from __future__ import annotations
import re


def _tokenize_query(query: str) -> list[str]:
    """Pull highlight-eligible tokens from the query.

    Strategy:
      - jieba.cut for Chinese-aware splitting (whitespace + punctuation falls out)
      - drop pure-whitespace / pure-punctuation segments
      - keep CJK tokens of any length; drop single-char ASCII (too noisy
        — "a" in many words would match everything)
      - de-dupe, preserve case from the query for the replacement template
        (the regex itself is case-insensitive)
    """
    import jieba
    seen: dict[str, None] = {}
    for tok in jieba.cut(query):
        t = tok.strip()
        if not t:
            continue
        if not any(ch.isalnum() or ord(ch) > 127 for ch in t):
            continue  # pure punctuation
        if len(t) == 1 and t.isascii():
            continue
        seen.setdefault(t, None)
    return list(seen)


def highlight_keywords(text: str, query: str) -> str:
    """Return ``text`` with every query token wrapped in ``**…**``.

    Idempotent only if called once — calling twice on an already-highlighted
    string will double-wrap. (No use case for that in v3; callers wrap
    once at search-output build time.)
    """
    if not text or not query:
        return text or ""
    tokens = _tokenize_query(query)
    if not tokens:
        return text
    # Longest-first to avoid shorter tokens consuming a prefix of a longer
    # match. With a single regex pass this matters: the regex engine tries
    # alternatives left-to-right and stops at first match, so longer ones
    # must come first.
    tokens.sort(key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(t) for t in tokens), flags=re.IGNORECASE)

    def _wrap(m: re.Match) -> str:
        return f"**{m.group(0)}**"

    return pattern.sub(_wrap, text)


def truncate(text: str, limit: int = 200) -> str:
    """Truncate to ``limit`` chars, appending '…' when something was cut."""
    if not text or len(text) <= limit:
        return text or ""
    return text[:limit] + "…"
