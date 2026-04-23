"""Pydantic models for v2 request/response bodies and shared types."""
from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel, Field


# ---------- shared ----------

LinkTargetType = Literal["card", "session"]
ObjectKind = Literal["card", "session"]


class ContentBlock(BaseModel):
    type: str  # text / code / thinking / ...
    text: str | None = None
    thinking: str | None = None
    language: str | None = None


class SessionRound(BaseModel):
    """Round as it appears in a Session (full fidelity)."""
    index: int
    round_id: str
    parent_id: str | None = None
    timestamp: str | None = None
    speaker: str | None = None
    role: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    is_sidechain: bool = False
    cwd: str | None = None
    usage: dict[str, Any] | None = None


class CardRound(BaseModel):
    """Round as it appears in a Card (flattened)."""
    role: str
    text: str
    thinking: str | None = None
    session_id: str
    index: int


class LinkRef(BaseModel):
    """Link in view/search responses (from the perspective of one endpoint)."""
    link_id: str
    target_id: str
    target_type: LinkTargetType
    comment: str | None = None
    ttl: int


# ---------- /v2/sessions ----------

class IngestRoundIn(BaseModel):
    round_id: str
    parent_id: str | None = None
    timestamp: str | None = None
    speaker: str | None = None
    role: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    is_sidechain: bool = False
    cwd: str | None = None
    usage: dict[str, Any] | None = None


class IngestSessionIn(BaseModel):
    session_id: str  # RAW platform id (no sess_ prefix); server prefixes on ingest
    source: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    sha256: str | None = None  # optional perf hint for skip-if-unchanged fast path
    rounds: list[IngestRoundIn] = Field(default_factory=list)


class IngestSessionOut(BaseModel):
    status: str
    session_id: str
    action: Literal["imported", "appended", "skipped", "partial_append"]
    round_count: int
    added_count: int
    overwrite_skipped: list[int] = Field(default_factory=list)


# ---------- /v2/cards ----------

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


# ---------- /v2/links ----------

class CreateLinkIn(BaseModel):
    source_id: str
    source_type: LinkTargetType
    target_id: str
    target_type: LinkTargetType
    comment: str | None = None


class CreateLinkOut(BaseModel):
    status: str = "ok"
    link_id: str
    ttl: int


# ---------- /v2/tags ----------

class TagsIn(BaseModel):
    session_id: str
    tags: list[str]


class TagsOut(BaseModel):
    status: str = "ok"
    tags: list[str]


# ---------- /v2/search ----------

class SearchIn(BaseModel):
    query: str
    where: str | None = None
    top_k: int | None = None


class CardHit(BaseModel):
    card_id: str
    rank: int
    score: float
    summary: str
    snippets: list[str] = Field(default_factory=list)
    links: list[LinkRef] = Field(default_factory=list)


class SessionHit(BaseModel):
    session_id: str
    rank: int
    score: float
    source: str
    tags: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)
    links: list[LinkRef] = Field(default_factory=list)


class SearchBucket(BaseModel):
    count: int
    results: list[Any]


class SearchOut(BaseModel):
    search_id: str
    query: str
    cards: SearchBucket
    sessions: SearchBucket


# ---------- /v2/view ----------

class ViewIn(BaseModel):
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


class ViewOut(BaseModel):
    type: Literal["card", "session"]
    read_at: str
    card: CardView | None = None
    session: SessionView | None = None
    links: list[LinkRef] = Field(default_factory=list)


# ---------- /v2/log ----------

class LogIn(BaseModel):
    id: str


class EventEntry(BaseModel):
    at: str
    kind: str
    detail: dict[str, Any]


class LogOut(BaseModel):
    type: Literal["card", "session"]
    card_id: str | None = None
    session_id: str | None = None
    events: list[EventEntry] = Field(default_factory=list)


# ---------- /v2/status ----------

class StatusOut(BaseModel):
    data_root: str
    settings_path: str
    status: str = "running"
    sessions_total: int
    cards_total: int
    links_total: int
    searches_total: int
    vector_provider: str
    relation_provider: str
    embedding_provider: str


# ---------- /v2/rebuild ----------

class RebuildOut(BaseModel):
    status: str = "ok"
    sessions: int
    cards: int
    searches_replayed: int
    events_replayed: int
    errors_count: int = 0
