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


class SourceProbe(BaseModel):
    """Light-weight inspection of one upstream artifact.

    Adapters return this to describe "what's the current state of this
    file/URL right now", without yielding the actual round payload. Sync
    uses it to compare against its checkpoint and decide whether to
    bother reading.
    """
    # adapter-side resource id (absolute file path, full URL, ...)
    source_id: str
    # platform raw id (no ``sess_`` prefix)
    session_id: str
    # whole-artifact content hash — semantics decided by the adapter
    # (sha256 of the file bytes, an HTTP ETag, ...). Used solely for
    # "did this change since last sync" short-circuit.
    sha256: str
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReadAfterResult(BaseModel):
    """Rounds strictly after a cursor, with hint info for the next call.

    ``next_line_offset`` is the adapter's hint for where to seek on the
    next read (line-based for jsonl, byte-based or pagination-cursor for
    other adapters — it's opaque to sync).
    """
    rounds: list[RoundInput] = Field(default_factory=list)
    next_line_offset: int = 0


class EnsureSessionRequest(BaseModel):
    """Look up a session's current ingest state without writing anything.

    ``session_id`` is the canonical minted id (``sess-<loc8>-<lastseg>``,
    produced by ``BaseAdapter.mint_session_id``). ``location`` /
    ``location_label`` carry through for fresh inserts that materialize
    a session row.
    """
    session_id: str
    source: str
    location: str = ""
    location_label: str | None = None


class EnsureSessionResponse(BaseModel):
    session_id: str  # canonical
    last_round_id: str | None = None
    round_count: int = 0


class AppendRoundsRequest(BaseModel):
    """Append new rounds to a session under optimistic-concurrency.

    ``session_id`` is the canonical minted id (``sess-<loc8>-<lastseg>``).
    ``location`` / ``location_label`` are stored on the sessions row at
    first insert (subsequent appends keep the existing values).
    """
    session_id: str
    source: str
    location: str = ""
    location_label: str | None = None
    expected_prev_round_id: str | None = None
    rounds: list[RoundInput] = Field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppendRoundsResponse(BaseModel):
    status: Literal["ok", "conflict"]
    session_id: str            # prefixed
    new_last_round_id: str | None = None
    appended_count: int = 0
    round_count: int = 0
    # Populated on status="conflict" — the server's actual cursor.
    actual_last_round_id: str | None = None
    # ── vector-index outcome (independent axis from append status) ──
    # ``status`` reports whether jsonl + SQLite write succeeded; these
    # fields report whether the LanceDB vector index for the appended
    # rounds was populated. ``index_status="partial"`` happens when
    # the embedder fails on some batches but not others (e.g. DashScope
    # 10-cap rejecting an 11+ chunk while the earlier 10-row batch
    # already landed). The background backfill task picks up degraded
    # sessions on the next server start.
    indexed_count: int = 0
    index_failed_count: int = 0
    index_status: Literal["ok", "partial", "failed"] = "ok"
    index_error: str | None = None
