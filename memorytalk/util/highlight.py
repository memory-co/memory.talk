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


def _compile_token_pattern(query: str) -> "re.Pattern[str] | None":
    tokens = _tokenize_query(query)
    if not tokens:
        return None
    # Longest-first to avoid shorter tokens consuming a prefix of a longer
    # match. With a single regex pass this matters: the regex engine tries
    # alternatives left-to-right and stops at first match, so longer ones
    # must come first.
    tokens.sort(key=len, reverse=True)
    return re.compile("|".join(re.escape(t) for t in tokens), flags=re.IGNORECASE)


def highlight_keywords(text: str, query: str) -> str:
    """Return ``text`` with every query token wrapped in ``**…**``.

    Idempotent only if called once — calling twice on an already-highlighted
    string will double-wrap. (No use case for that in v3; callers wrap
    once at search-output build time.)
    """
    if not text or not query:
        return text or ""
    pattern = _compile_token_pattern(query)
    if pattern is None:
        return text
    return pattern.sub(lambda m: f"**{m.group(0)}**", text)


def truncate(text: str, limit: int = 200) -> str:
    """Truncate to ``limit`` chars, appending '…' when something was cut."""
    if not text or len(text) <= limit:
        return text or ""
    return text[:limit] + "…"


def make_snippet(text: str, query: str, head_chars: int = 100) -> str:
    """Display-budget excerpt of ``text`` for search hits.

    Two modes (decided by token presence — NOT by which recall pipeline
    produced the hit; see docs/structure/v3/search-result.md):

    - **Keyword window**: when any query token occurs in ``text``, return a
      ~``head_chars``-wide window centered on the earliest match, with
      query tokens wrapped in ``**…**`` and ``…`` prefix/suffix when the
      window was trimmed at either edge.
    - **Head preview**: when no token matches (typical for pure vector
      recall), return the first ``head_chars`` characters with a ``…``
      suffix when truncated. No highlighting (by definition there's
      nothing to highlight).
    """
    if not text:
        return ""
    if head_chars <= 0 or len(text) <= head_chars:
        # Whole text fits the budget — still highlight if applicable.
        return highlight_keywords(text, query)

    pattern = _compile_token_pattern(query) if query else None
    match = pattern.search(text) if pattern is not None else None
    if match is None:
        # Vector-only hit (or query with no usable tokens). Head preview.
        return text[:head_chars] + "…"

    # Center a window of head_chars around the earliest match. When the
    # match is near either edge, shift the window so we still fill the
    # budget instead of returning a half-empty window.
    radius = head_chars // 2
    start = max(0, match.start() - radius)
    end = min(len(text), start + head_chars)
    if end - start < head_chars:
        start = max(0, end - head_chars)

    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return highlight_keywords(snippet, query)
