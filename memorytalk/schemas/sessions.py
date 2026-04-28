"""POST /v2/sessions request/response schemas."""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, Field

from memorytalk.schemas.shared import ContentBlock


class IngestRound(BaseModel):
    round_id: str
    parent_id: str | None = None
    timestamp: str | None = None
    speaker: str | None = None
    role: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    is_sidechain: bool = False
    cwd: str | None = None
    usage: dict[str, Any] | None = None


class IngestSessionRequest(BaseModel):
    session_id: str  # RAW platform id (no sess_ prefix); server prefixes on ingest
    source: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    sha256: str | None = None  # optional perf hint for skip-if-unchanged fast path
    rounds: list[IngestRound] = Field(default_factory=list)


class IngestSessionResponse(BaseModel):
    status: str
    session_id: str
    action: Literal["imported", "appended", "skipped", "partial_append"]
    round_count: int
    added_count: int
    overwrite_skipped: list[int] = Field(default_factory=list)
