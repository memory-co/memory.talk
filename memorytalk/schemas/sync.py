"""POST /v3/sync/start, POST /v3/sync/stop, GET /v3/sync/status."""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, Field


class _IngestStats(BaseModel):
    discovered: int = 0
    imported: int = 0
    appended: int = 0
    skipped: int = 0
    overwrite_warnings: int = 0
    errors: int = 0
    # Sessions where the LanceDB index didn't catch up on this run
    # (status=partial / failed). Distinct from ``errors`` (which counts
    # sync-layer failures like probe/read_after); ``index_errors``
    # specifically signals "data is in jsonl/SQLite but search can't
    # see it yet" — the backfill loop will retry.
    index_errors: int = 0


class SyncStartResponse(BaseModel):
    status: Literal["started", "already_running"]
    adapters: list[str] = Field(default_factory=list)
    backfill: _IngestStats | None = None
    uptime_seconds: float | None = None  # only when already_running


class SyncStopResponse(BaseModel):
    status: Literal["stopped", "not_running"]
    uptime_seconds: float | None = None
    totals: _IngestStats | None = None


class _SyncWatchedRoot(BaseModel):
    path: str
    ok: bool
    reason: str | None = None  # e.g. "missing"


class _SyncRecentEvent(BaseModel):
    at: str
    session_id: str
    # imported / rounds_appended / rounds_overwrite_skipped / error /
    # index_partial / index_failed
    event: str
    rounds: int | None = None
    rounds_skipped: int | None = None
    error: str | None = None
    # Populated for index_partial / index_failed events.
    indexed: int | None = None
    index_failed: int | None = None


class _IndexHealth(BaseModel):
    """Snapshot of how complete the LanceDB rounds index is. Aggregated
    on each ``GET /v3/sync/status`` from the ``sessions`` table — fields
    backed by ``indexed_round_count`` / ``round_count``."""
    total_sessions: int = 0
    total_rounds: int = 0
    indexed_rounds: int = 0
    missing_rounds: int = 0
    degraded_sessions: int = 0
    backfill_status: Literal["running", "idle", "disabled"] = "idle"
    last_index_error: str | None = None


class _SyncLastRun(BaseModel):
    start: str
    stop: str
    duration_seconds: float
    totals: _IngestStats


class SyncStatusResponse(BaseModel):
    status: Literal["running", "stopped"]
    uptime_seconds: float | None = None
    adapters: list[str] = Field(default_factory=list)
    watching: list[_SyncWatchedRoot] = Field(default_factory=list)
    totals: _IngestStats | None = None
    last_event_at: str | None = None
    recent: list[_SyncRecentEvent] = Field(default_factory=list)
    last_run: _SyncLastRun | None = None
    # Always returned (even when sync is stopped) — index health is a
    # property of the data root, not the sync watcher's runtime state.
    index: _IndexHealth = Field(default_factory=_IndexHealth)
