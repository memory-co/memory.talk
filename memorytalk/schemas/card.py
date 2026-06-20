"""v4 read models: Card (== Issue), Position, CardLink, CardSession.

Field names mirror docs/structure/v4/. credence is NOT a stored field --
the service computes it at read time and injects it into response DTOs
(defined in the service plan), so it is absent here.

A Position has no global id -- it is identified by ``(card_id, position)``
where ``position`` is a card-scoped seq ``p<n>`` and is addressed
``card_id#p<n>``. A CardLink is likewise identified by ``(card_id, link)``
(seq ``l<n>``, addressed ``card_id#l<n>``) and is a governed object with a
``claim`` + argument tallies (credence applies to links too).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Position(BaseModel):
    card_id: str
    position: str                       # card-scoped seq 'p<n>'
    claim: str
    created_at: str
    up_count: int = 0
    down_count: int = 0
    neutral_count: int = 0
    review_count: int = 0
    scope: str = ""
    forked_from: str | None = None      # 'p<n>' | None (lineage)


class CardLink(BaseModel):
    card_id: str                       # subject (NOT from/to)
    link: str                          # card-scoped seq 'l<n>'
    type: Literal[
        "specializes", "suggested_by", "questions", "replaces", "related"
    ]
    target_id: str
    target_type: Literal["card", "position"]
    claim: str = ""
    up_count: int = 0
    down_count: int = 0
    neutral_count: int = 0
    review_count: int = 0
    created_at: str


class CardSession(BaseModel):
    card_id: str
    session_id: str
    mark: str = ""                      # session-scoped seq 'm<n>' (provenance)
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
