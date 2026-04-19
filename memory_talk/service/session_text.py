"""Flatten session rounds into a single text blob for FTS indexing."""
from __future__ import annotations

from memory_talk.models.session import Round


def rounds_to_text(rounds: list[Round]) -> str:
    """Concatenate all text-bearing content blocks from rounds, newline-separated.

    TextBlock / CodeBlock expose `.text`; ThinkingBlock exposes `.thinking`.
    """
    parts: list[str] = []
    for r in rounds:
        for block in r.content:
            value = getattr(block, "text", None)
            if value is None:
                value = getattr(block, "thinking", None)
            if value:
                parts.append(value)
    return "\n".join(parts)
