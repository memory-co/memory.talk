"""GET /v3/sync/status.

Sync is a configuration switch (``settings.sync.enabled``), not a CLI
control plane — there is no longer a ``start`` or ``stop`` route. The
lifespan reads the flag on server startup and spins the watcher up if
asked.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/sync/status")
async def get_sync_status(request: Request, limit: int = Query(5, ge=0, le=20)):
    config = request.app.state.config
    watcher = request.app.state.sync
    if not config.settings.sync.enabled:
        return {"status": "disabled"}
    if not watcher.running:
        # enabled=True but the watcher isn't live → lifespan auto-start
        # failed. The exact exception isn't captured here; users can find
        # it in stderr of the server process.
        return {"status": "error", "error": "watcher not running"}
    return {
        "status": "running",
        "phase": watcher.phase,
        "uptime_seconds": watcher.uptime_seconds,
        "adapters": watcher.adapter_names(),
        "watching": watcher.watching(),
        "totals": watcher.totals(),
        "last_event_at": (watcher.recent(1) or [{}])[0].get("at"),
        "recent": watcher.recent(limit=limit),
    }
