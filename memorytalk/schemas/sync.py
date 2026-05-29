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
    # ``<source>@<label>`` for the endpoint that produced this event.
    # Empty string allowed for legacy paths that don't have an
    # adapter handle (e.g. lifespan-level failures).
    endpoint: str = ""
    rounds: int | None = None
    rounds_skipped: int | None = None
    error: str | None = None
    # Populated for index_partial / index_failed events.
    indexed: int | None = None
    index_failed: int | None = None


class _Endpoint(BaseModel):
    """One configured sync endpoint. Surfaced in ``sync/status`` so the
    user can see at a glance which sources are wired up + whether
    they're reachable."""
    source: str
    location: str
    label: str
    ok: bool
    reason: str | None = None  # populated when ok=False (e.g. ``missing``)


class _IndexHealthByEndpoint(BaseModel):
    """Per-endpoint slice of the index health snapshot. Endpoint key is
    ``<source>@<label>``."""
    endpoint: str
    source: str
    location: str
    label: str
    sessions: int
    rounds: int
    indexed: int
    missing: int
    degraded: int


class _LanceHealth(BaseModel):
    """0.8.x: surface the LanceDB layer's own health signals so EMFILE
    risk is visible *before* search starts 500-ing.

    Field choices follow issue #4 §6.6 — we want to spot two things
    that the index-counts view above can't catch:

      1. **Write pipeline:** is the IndexWriteBuffer keeping up, or are
         flushes failing / pending rows piling up?
      2. **Search pipeline:** has compaction been running, and has the
         process needed to recover from EMFILE since boot?
    """
    # IndexWriteBuffer state.
    pending_vector_rows: int = 0
    last_flush_at: str | None = None
    last_flush_error: str | None = None
    flush_count_since_boot: int = 0
    # IndexBackfill compaction state (last attempt seconds-ago).
    last_compaction_at: str | None = None
    last_compaction_error: str | None = None
    # LanceStore EMFILE recovery count + most recent occurrence.
    emfile_recoveries_since_boot: int = 0
    last_emfile_at: str | None = None
    # Process fd ceiling — flagged as observability since the issue's
    # whole story turns on macOS-launchd 256 default.
    fd_soft_limit: int | None = None
    fd_hard_limit: int | None = None


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
    # Per-endpoint breakdown so the CLI can render one row per source.
    by_endpoint: list[_IndexHealthByEndpoint] = Field(default_factory=list)
    # 0.8.x — LanceDB-layer health signals (write pipeline + EMFILE).
    # Separate sub-block so the index-completion picture above stays
    # uncluttered by lower-level operational signals.
    lance: _LanceHealth = Field(default_factory=_LanceHealth)


class _SyncLastRun(BaseModel):
    start: str
    stop: str
    duration_seconds: float
    totals: _IngestStats


class SyncStatusResponse(BaseModel):
    status: Literal["running", "stopped"]
    uptime_seconds: float | None = None
    adapters: list[str] = Field(default_factory=list)
    # New 0.7.x: structured per-endpoint info. Replaces ``adapters`` /
    # ``watching`` for callers that want a unified view. Kept the old
    # fields for back-compat with older API consumers.
    endpoints: list[_Endpoint] = Field(default_factory=list)
    watching: list[_SyncWatchedRoot] = Field(default_factory=list)
    totals: _IngestStats | None = None
    # Per-endpoint totals (same keys as ``totals``, keyed by ``<source>@<label>``).
    totals_by_endpoint: dict[str, _IngestStats] = Field(default_factory=dict)
    last_event_at: str | None = None
    recent: list[_SyncRecentEvent] = Field(default_factory=list)
    last_run: _SyncLastRun | None = None
    # Always returned (even when sync is stopped) — index health is a
    # property of the data root, not the sync watcher's runtime state.
    index: _IndexHealth = Field(default_factory=_IndexHealth)
