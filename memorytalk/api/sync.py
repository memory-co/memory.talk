"""GET /v3/sync/status.

Sync is a configuration switch (``settings.sync.enabled``), not a CLI
control plane — there is no longer a ``start`` or ``stop`` route. The
lifespan reads the flag on server startup and spins the watcher up if
asked.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter()


async def _gather_lance_health(state) -> dict:
    """Collect vector-layer observability for ``index.lance``.

    Pulls compaction + EMFILE-recovery state from the searchbase
    instance's ``health().detail``. The write path is now immediate
    (no IndexWriteBuffer), so the legacy buffer fields report idle.
    All fields default to safe zeros / None when searchbase is absent
    so a partially-disabled boot still returns a well-shaped response.
    """
    searchbase = getattr(state, "searchbase", None)
    detail: dict = {}
    if searchbase is not None:
        try:
            detail = (await searchbase.health()).detail
        except Exception:
            detail = {}

    soft = hard = None
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (ImportError, OSError):
        # Windows / sandboxed envs — leave None so the field's
        # absence is the signal.
        pass

    return {
        # Writes are immediate now — no buffer to drain.
        "pending_vector_rows": 0,
        "last_flush_at": None,
        "last_flush_error": None,
        "flush_count_since_boot": 0,
        "last_compaction_at": detail.get("last_compact_at_iso"),
        "last_compaction_error": detail.get("last_compact_error"),
        "emfile_recoveries_since_boot": detail.get("emfile_recoveries", 0),
        "last_emfile_at": detail.get("last_emfile_at_iso"),
        "fd_soft_limit": soft,
        "fd_hard_limit": hard,
    }


@router.get("/sync/status")
async def get_sync_status(request: Request, limit: int = Query(5, ge=0, le=20)):
    config = request.app.state.config
    watcher = request.app.state.sync
    db = request.app.state.db

    # Index health is independent of sync watcher state — even when
    # sync is disabled the index can be degraded (e.g. partial backfill
    # from a previous run). Compute it unconditionally so callers always
    # see the data-completeness picture.
    index = await db.sessions.get_index_health()
    index["by_endpoint"] = await db.sessions.get_index_health_by_endpoint()
    backfill = getattr(request.app.state, "backfill", None)
    index["backfill_status"] = (
        backfill.status if backfill is not None else "disabled"
    )
    index["last_index_error"] = (
        backfill.last_error if backfill is not None else None
    )
    index["lance"] = await _gather_lance_health(request.app.state)

    if not config.settings.sync.enabled:
        return {"status": "disabled", "index": index}
    if not watcher.running:
        return {"status": "error", "error": "watcher not running", "index": index}

    totals = watcher.totals()
    return {
        "status": "running",
        "phase": watcher.phase,
        "uptime_seconds": watcher.uptime_seconds,
        "adapters": watcher.adapter_names(),
        "endpoints": watcher.endpoint_info(),
        "watching": watcher.watching(),
        "totals": totals.get("_total", totals),
        "totals_by_endpoint": {k: v for k, v in totals.items() if k != "_total"},
        "last_event_at": (watcher.recent(1) or [{}])[0].get("at"),
        "recent": watcher.recent(limit=limit),
        "index": index,
    }
