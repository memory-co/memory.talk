"""Insight + InsightStats + SourceInsight + InsightRound."""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, Field


class SourceInsight(BaseModel):
    """One ``source_cards[]`` entry on a card.

    ``relation`` tags the kind of link. Created at card-write time and
    immutable thereafter; new relations can be added by writing new cards.
    """
    card_id: str
    relation: Literal["derives_from", "supersedes"]


class InsightRound(BaseModel):
    """A round as embedded inside a card (post-expansion).

    Different from ``schemas.session.Round``: only the bits needed to
    render the card are kept — role, text, plus the source-session
    coordinates so callers can re-deref the original.
    """
    role: str
    text: str
    thinking: str | None = None
    session_id: str
    index: int


class InsightStats(BaseModel):
    """Runtime forum-dynamics signals.

    Bucketed by intent: ``review_*`` are *real discussion* (active
    engagement via :class:`Review`); ``read_count`` and ``recall_count``
    are *just passing by* (passive use). The split matters for the
    sinking/floating formula — see docs/cli/v3/search.md.
    """
    review_up: int = 0
    review_down: int = 0
    review_neutral: int = 0
    review_count: int = 0
    read_count: int = 0
    recall_count: int = 0


class Insight(BaseModel):
    """The shape ``POST /v3/read`` returns for a card id."""
    card_id: str
    insight: str
    source_cards: list[SourceInsight] = Field(default_factory=list)
    rounds: list[InsightRound] = Field(default_factory=list)
    stats: InsightStats = Field(default_factory=InsightStats)
    created_at: str
