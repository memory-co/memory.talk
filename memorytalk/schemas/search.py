"""POST /v2/search request/response schemas."""
from __future__ import annotations
from typing import Any

from pydantic import BaseModel, Field

from memory_talk_v2.schemas.shared import LinkRef


class SearchRequest(BaseModel):
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


class SearchResponse(BaseModel):
    search_id: str
    query: str
    cards: SearchBucket
    sessions: SearchBucket
