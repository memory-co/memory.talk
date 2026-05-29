"""POST /v3/search — request + response."""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, Field

from memorytalk.schemas.card import CardStats


class SearchRequest(BaseModel):
    query: str = ""
    where: str | None = None
    top_k: int | None = None  # falls back to settings.search.default_top_k
    # ── 0.8.x: --recall debug lens ──────────────────────────────────
    # When True, the search service mimics ``RecallService``:
    # cards-only, raw RRF relevance (no ranking_formula), and (when
    # ``recall_session_id`` is supplied) dedup against that session's
    # recall_log. Strictly read-only — does NOT bump recall_count or
    # write recall_log entries. Use it to tune queries against the
    # live recall behavior without polluting state.
    recall_mode: bool = False
    recall_session_id: str | None = None


class _SessionHitContext(BaseModel):
    index: int
    role: str
    text: str


class SessionHit(BaseModel):
    index: int
    role: str
    text: str
    score: float
    # ISO 8601 UTC timestamp of when this round happened on the source
    # platform (e.g. claude-code). Optional: some adapters or older
    # rounds may not have one — render falls back to "no time".
    timestamp: str | None = None
    context_before: _SessionHitContext | None = None
    context_after: _SessionHitContext | None = None


class CardResult(BaseModel):
    type: Literal["card"] = "card"
    rank: int
    score: float
    card_id: str
    insight: str
    # ISO 8601 UTC timestamp of card creation. Mirror of cards.created_at.
    created_at: str
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
    # 0.8.x — discriminator between normal search and the --recall
    # debug lens, so audit / programmatic consumers can tell them apart
    # without comparing top-level body shapes.
    mode: Literal["search", "recall"] = "search"
    # Set only on recall-mode + session_id supplied. Lets the JSON
    # consumer see the dedup scope used to produce these results.
    session_id: str | None = None
    results: list[CardResult | SessionResult] = Field(default_factory=list)
