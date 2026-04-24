"""POST /v2/cards request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CardRoundsItemIn(BaseModel):
    session_id: str  # must be sess_<...>
    indexes: str     # "11-15" or "3,7,12"


class CreateCardIn(BaseModel):
    summary: str
    rounds: list[CardRoundsItemIn] = Field(default_factory=list)
    card_id: str | None = None
    from_search_id: str | None = None


class CreateCardOut(BaseModel):
    status: str = "ok"
    card_id: str
