"""POST /v2/view request/response schemas."""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, Field

from memorytalk.schemas.shared import CardRound, LinkRef, SessionRound


class ViewRequest(BaseModel):
    id: str


class CardView(BaseModel):
    card_id: str
    summary: str
    rounds: list[CardRound] = Field(default_factory=list)
    created_at: str
    ttl: int


class SessionView(BaseModel):
    session_id: str
    source: str
    created_at: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    rounds: list[SessionRound] = Field(default_factory=list)


class ViewResponse(BaseModel):
    type: Literal["card", "session"]
    read_at: str
    card: CardView | None = None
    session: SessionView | None = None
    links: list[LinkRef] = Field(default_factory=list)
