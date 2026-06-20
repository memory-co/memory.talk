"""``#…？`` issue extraction from a mark's free text.

A mark's ``mark`` field is free-form "annotation while reading". Issues are
marked in-place with the ``#…？`` syntax: each ``#`` starts an issue and the
**first** ``？`` (full-width) or ``?`` (half-width) closes it; the trimmed
text between is one issue. A mark may carry zero, one, or many issues.

This is the seam the session-mark write path turns into cards: every issue
text is embedded and collided against the ``cards`` (issue) vector library —
miss → new card, hit → linked card (see ``service/session_marks.py``).

Honest boundary (docs/works/v4/session-mark.md §9): a ``#`` with no closing
``？``/``?`` is **not** an issue — it's just a literal ``#`` in prose. Only a
``#`` that finds its terminator counts.
"""
from __future__ import annotations

# Issue terminators: full-width ``？`` is the default; half-width ``?`` is
# also accepted (docs §9 "？分隔").
_TERMINATORS = ("？", "?")


def parse_issues(text: str) -> list[str]:
    """Extract every ``#…？`` issue from ``text``.

    Returns the trimmed issue bodies in document order. A ``#`` without a
    following terminator is ignored (it's literal prose, not an issue), and
    an empty/whitespace-only body is dropped (``#？`` yields nothing).

    >>> parse_issues("配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？他其实想要可重连会话。")
    ['为什么 pty 会让用户想到 tmux']
    >>> parse_issues("a #q1? b #q2？ c")
    ['q1', 'q2']
    >>> parse_issues("no issue here # just a hash")
    []
    """
    if not text or not isinstance(text, str):
        return []
    issues: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "#":
            i += 1
            continue
        # Find the nearest terminator after this '#'.
        end = _find_terminator(text, i + 1)
        if end == -1:
            # Unterminated '#': literal prose, not an issue. Stop scanning
            # for more '#' starts only past this one (there may be a later
            # well-formed issue), so just advance one char.
            i += 1
            continue
        body = text[i + 1:end].strip()
        if body:
            issues.append(body)
        # Resume scanning *after* the terminator so a single terminator
        # can't close two issues.
        i = end + 1
    return issues


def _find_terminator(text: str, start: int) -> int:
    """Index of the nearest ``？``/``?`` at or after ``start``; -1 if none."""
    best = -1
    for term in _TERMINATORS:
        pos = text.find(term, start)
        if pos != -1 and (best == -1 or pos < best):
            best = pos
    return best
