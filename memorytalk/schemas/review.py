"""Review request/response schemas — list + detail."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewSessionSummary(BaseModel):
    session_id: str
    session_exist: bool
    round_count: int
    cards_injected: int
    first_at: str
    last_at: str
    last_query: str | None = None


class ReviewListResponse(BaseModel):
    sessions: list[ReviewSessionSummary] = Field(default_factory=list)


class ReviewHit(BaseModel):
    card_id: str
    rank: int
    summary: str = ""  # denormalized from cards.summary at recall time


class ReviewRound(BaseModel):
    round_count: int
    query: str
    recalled_at: str
    hits: list[ReviewHit] = Field(default_factory=list)


class ReviewDetailResponse(BaseModel):
    session_id: str
    session_exist: bool
    round_count: int
    cards_injected: int
    first_at: str
    last_at: str
    last_query: str | None = None
    rounds: list[ReviewRound] = Field(default_factory=list)
