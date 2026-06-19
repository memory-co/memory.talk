"""v4 credence — the answer-quality score, computed at read time.

credence is **never stored** (no column, no write-back). The Position row
keeps only the raw argument tallies (up/down/neutral_count); the service
derives credence whenever it sorts or returns Positions.

Formula (decided): ``credence = up_count − down_count``. Neutral arguments
(``argument == 0``) count toward review_count / engagement but do not move
credence. The Wilson lower bound is the documented alternative; this build
fixes up−down.
"""
from __future__ import annotations


def credence(up_count: int, down_count: int) -> int:
    """The answer-quality score for a Position. up − down."""
    return up_count - down_count


def with_credence(position_row: dict, last_reviewed_at: str | None) -> dict:
    """Return a copy of a ``positions`` row with the derived ``credence``
    and ``last_reviewed_at`` (tiebreak key) injected. ``last_reviewed_at``
    falls back to ``created_at`` when the Position has no reviews yet."""
    return {
        **position_row,
        "credence": credence(position_row["up_count"], position_row["down_count"]),
        "last_reviewed_at": last_reviewed_at or position_row["created_at"],
    }


def sort_key(injected_position: dict):
    """Sort key for "current answer" ordering: credence DESC, then most
    recent review DESC. Use as ``sorted(..., key=sort_key, reverse=True)``."""
    return (injected_position["credence"], injected_position["last_reviewed_at"])
