"""Session + Round + ContentBlock + Ingest request/response."""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, Field


class ContentBlock(BaseModel):
    """One block inside a Round's ``content`` array.

    Free-form on purpose: platforms emit text / code / thinking / tool_use
    / tool_result etc. We preserve them verbatim and let downstream
    consumers (read display, FTS extraction) project as needed.
    """
    type: str
    # Common shapes are surfaced explicitly so consumers can hit fields
    # without dict.get; everything else falls into ``extra``.
    text: str | None = None
    language: str | None = None
    thinking: str | None = None
    # Anything else (tool_use input dict, tool_result content array, etc.).
    model_config = {"extra": "allow"}


class RoundInput(BaseModel):
    """Single round as accepted by ``POST /v3/sessions`` ingest.

    Note: ``index`` is **not** an input — the server assigns it on first
    write and keeps it stable across re-ingests. Adapters supply
    ``round_id`` (platform uuid) which the server uses to align with
    already-stored rounds.
    """
    round_id: str
    parent_id: str | None = None
    timestamp: str | None = None
    speaker: str | None = None
    role: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    is_sidechain: bool = False
    cwd: str | None = None
    usage: dict[str, Any] | None = None


class Round(RoundInput):
    """Stored round — same as RoundInput plus the server-assigned ``index``."""
    index: int


class Session(BaseModel):
    """The shape that ``POST /v3/read`` returns for a session id."""
    session_id: str
    source: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    rounds: list[Round] = Field(default_factory=list)


class IngestSessionRequest(BaseModel):
    """Sync watcher writes platform sessions through this endpoint.

    ``session_id`` here is the **platform raw id** (no ``sess_`` prefix);
    the server prefixes on first write and returns the prefixed form.
    """
    session_id: str
    source: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    sha256: str
    rounds: list[RoundInput] = Field(default_factory=list)


class IngestSessionResponse(BaseModel):
    status: Literal["ok"] = "ok"
    session_id: str  # prefixed
    action: Literal["imported", "appended", "skipped", "partial_append"]
    round_count: int
    added_count: int = 0
    overwrite_skipped: list[int] = Field(default_factory=list)
