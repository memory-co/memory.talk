"""Talk-Card model — the core memory unit."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RawRef(BaseModel):
    """Pointer to original conversation location."""

    session_id: str
    round_start: int
    round_end: int


class CardLink(BaseModel):
    """Link between two cards."""

    source_card_id: str
    target_card_id: str
    link_type: str  # temporal / topical / causal
    weight: float = 1.0


class TalkCard(BaseModel):
    """A memory unit extracted from conversation, ≤1024 tokens."""

    card_id: str
    cognition_summary: str  # one sentence — embedding anchor
    compressed_rounds: str  # condensed conversation content
    raw_ref: RawRef
    links: list[CardLink] = []
    token_count: Optional[int] = None
    created_at: datetime = datetime.now()
