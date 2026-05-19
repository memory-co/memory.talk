"""POST /v3/sync/start, POST /v3/sync/stop, GET /v3/sync/status."""
from __future__ import annotations
import datetime as _dt

from fastapi import APIRouter, Query, Request

router = APIRouter()


def _iso_from_monotonic(uptime: float) -> str:
    """Convert an uptime (monotonic seconds) back to a wall-clock ISO timestamp.

    Used by status to report ``last_event_at``-style fields; for events
    happening "now" prefer ``_ISO`` from the service module.
    """
    return _dt.datetime.fromtimestamp(
        _dt.datetime.now().timestamp() - uptime, tz=_dt.UTC,
    ).isoformat(timespec="seconds").replace("+00:00", "Z")


@router.post("/sync/start")
async def post_sync_start(request: Request):
    watcher = request.app.state.sync
    return await watcher.start()


@router.post("/sync/stop")
async def post_sync_stop(request: Request):
    watcher = request.app.state.sync
    return await watcher.stop()


@router.get("/sync/status")
async def get_sync_status(request: Request, limit: int = Query(5, ge=0, le=20)):
    watcher = request.app.state.sync
    if not watcher.running:
        return {"status": "stopped", "last_run": watcher.last_run()}
    return {
        "status": "running",
        "uptime_seconds": watcher.uptime_seconds,
        "adapters": watcher.adapter_names(),
        "watching": watcher.watching(),
        "totals": watcher.totals(),
        "last_event_at": (watcher.recent(1) or [{}])[0].get("at"),
        "recent": watcher.recent(limit=limit),
    }
