"""POST /v2/cards request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CardRoundsItem(BaseModel):
    session_id: str  # must be sess_<...>
    indexes: str     # "11-15" or "3,7,12"


class CreateCardRequest(BaseModel):
    summary: str
    rounds: list[CardRoundsItem] = Field(default_factory=list)
    card_id: str | None = None
    from_search_id: str | None = None


class CreateCardResponse(BaseModel):
    status: str = "ok"
    card_id: str
