"""Review — a "reply" to a card with a stance (+1 / 0 / -1) and a comment.

This is the core *real discussion* signal in v3's forum dynamics.
"""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel


class Review(BaseModel):
    review_id: str
    card_id: str
    session_id: str
    # Validated at the indexes-parser boundary; stored as the original string
    # so the client display can echo "20-25" or "3,7,12" verbatim.
    indexes: str
    # Stance — 1 supports / 0 neutral (annotation only) / -1 refutes.
    score: Literal[-1, 0, 1]
    comment: str | None = None
    created_at: str
