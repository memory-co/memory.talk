"""v4 read models: Card (== Issue), Position, CardLink, CardSession.

Field names mirror docs/structure/v4/. credence is NOT a stored field --
the service computes it at read time and injects it into response DTOs
(defined in the service plan), so it is absent here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Position(BaseModel):
    position_id: str
    card_id: str
    claim: str
    created_at: str
    up_count: int = 0
    down_count: int = 0
    neutral_count: int = 0
    review_count: int = 0
    scope: str = ""
    forked_from_position_id: str | None = None


class CardLink(BaseModel):
    card_id: str                       # subject (NOT from/to)
    type: Literal[
        "specializes", "suggested_by", "questions", "replaces", "related"
    ]
    target_id: str
    target_type: Literal["card", "position"]
    created_at: str


class CardSession(BaseModel):
    card_id: str
    session_id: str
    position_id: str = ""               # "" = card-level association
    indexes: str
    created_at: str


class Card(BaseModel):
    card_id: str
    issue: str
    created_at: str
    position_count: int = 0
    link_count: int = 0
    positions: list[Position] = Field(default_factory=list)
    links: list[CardLink] = Field(default_factory=list)
    sessions: list[CardSession] = Field(default_factory=list)
