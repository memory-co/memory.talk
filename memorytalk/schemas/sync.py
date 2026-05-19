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
    event: str  # imported / rounds_appended / rounds_overwrite_skipped / error
    rounds: int | None = None
    rounds_skipped: int | None = None
    error: str | None = None


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
