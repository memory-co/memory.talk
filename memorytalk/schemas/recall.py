"""POST /v2/recall request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RecallRequest(BaseModel):
    session_id: str          # raw or sess_-prefixed; service prefixes
    query: str
    top_k: int | None = None  # default from settings.recall.default_top_k


class RecallHit(BaseModel):
    card_id: str
    summary: str


class RecallResponse(BaseModel):
    session_id: str
    round_count: int
    query: str
    recalled: list[RecallHit] = Field(default_factory=list)
    skipped_already_recalled: list[str] = Field(default_factory=list)
