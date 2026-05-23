"""POST /v3/search — request + response."""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, Field

from memorytalk.schemas.card import CardStats


class SearchRequest(BaseModel):
    query: str = ""
    where: str | None = None
    top_k: int | None = None  # falls back to settings.search.default_top_k
    # When false (default), apply per-type "strong-floor" filter: if any
    # result of that type clears the floor, hide everything below it; if
    # nothing clears the floor, return the whole bucket. To inspect what
    # was filtered, re-issue with show_all=true. See service/search.py
    # for the hardcoded floors (session 0.02, card 0.1) and rationale.
    show_all: bool = False


class _SessionHitContext(BaseModel):
    index: int
    role: str
    text: str


class SessionHit(BaseModel):
    index: int
    role: str
    text: str
    score: float
    context_before: _SessionHitContext | None = None
    context_after: _SessionHitContext | None = None


class CardResult(BaseModel):
    type: Literal["card"] = "card"
    rank: int
    score: float
    card_id: str
    insight: str
    stats: CardStats = Field(default_factory=CardStats)


class SessionResult(BaseModel):
    type: Literal["session"] = "session"
    rank: int
    score: float
    session_id: str
    source: str
    hit_count: int
    hits_shown: int
    hits: list[SessionHit] = Field(default_factory=list)


class SearchResponse(BaseModel):
    search_id: str
    query: str
    count: int
    # Number of results filtered out by the strong-floor rule (sum across
    # both types). 0 when ``show_all=true`` or when nothing was filtered.
    hidden_count: int = 0
    results: list[CardResult | SessionResult] = Field(default_factory=list)
