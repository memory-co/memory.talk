"""Session ingest endpoints — cursor-based, append-only.

Two routes; both are direct projections of the in-process
``IngestService`` methods. External orchestrators (CI runners, the sync
watcher when it eventually splits out-of-process, scripts) use this
pair to push session data under optimistic concurrency.

  POST /v3/sessions/ensure   — read the server's current cursor for a
                                (source, session_id). Returns the
                                prefixed session id, last_round_id
                                (None if unknown), round_count.

  POST /v3/sessions/append   — write rounds strictly after
                                ``expected_prev_round_id``. Returns
                                ``status="ok"`` with the new cursor on
                                success, or ``status="conflict"`` with
                                the server's actual cursor when the
                                expected value doesn't match. The caller
                                is expected to recompute and retry.

There is no whole-session "ingest" endpoint any more — the legacy
``POST /v3/sessions`` shim has been removed alongside the merge-with-
overwrite-detection protocol it papered over.
"""
from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.schemas import (
    AppendRoundsRequest, AppendRoundsResponse,
    EnsureSessionRequest, EnsureSessionResponse,
    SessionListResponse, SessionMeta,
    TagPatchRequest, TagResponse,
)
from memorytalk.service import IngestServiceError
from memorytalk.util.tags import TagValidationError, apply_patch


router = APIRouter()


@router.post("/sessions/ensure", response_model=EnsureSessionResponse)
async def post_sessions_ensure(payload: EnsureSessionRequest, request: Request):
    try:
        return await request.app.state.ingest.ensure_session(payload)
    except IngestServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/append", response_model=AppendRoundsResponse)
async def post_sessions_append(payload: AppendRoundsRequest, request: Request):
    try:
        return await request.app.state.ingest.append_rounds(payload)
    except IngestServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 0.8.x: list + tag maintenance ──────────────────────────────────


def _parse_iso(value: str | None, *, field: str) -> str | None:
    """Validate that ``value`` is parseable as ISO 8601; return as-is.

    We don't reformat — SQL comparisons treat the column as plain TEXT
    (lexicographic ISO ordering is intentional), so leaving the
    string as the caller supplied it keeps comparisons deterministic.
    """
    if value is None:
        return None
    try:
        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail=f"invalid ISO 8601 in '{field}': {value!r}",
        )
    return value


def _split_tags(raw: list[str]) -> tuple[dict[str, str], list[str]]:
    """Split repeated ``?tag=...`` query params into two collections.

    ``K=V`` → equality match (``tag_eq[K] = V``)
    ``K``   → presence match (``tag_present.append(K)``)

    Same key in both forms is allowed (intersect: must exist AND equal V).
    """
    eq: dict[str, str] = {}
    present: list[str] = []
    for item in raw:
        if not item:
            continue
        if "=" in item:
            k, _, v = item.partition("=")
            if not k:
                raise HTTPException(
                    status_code=400, detail=f"tag query param missing key: {item!r}",
                )
            eq[k] = v
        else:
            present.append(item)
    # Key-shape validation deferred to the repo's per-key lookup —
    # SQLite json_extract on a malformed path just returns NULL, which
    # produces an empty result rather than a crash; we don't strictly
    # need to reject here. But for symmetry with PATCH errors we do.
    from memorytalk.util.tags import validate_key
    try:
        for k in eq:
            validate_key(k)
        for k in present:
            validate_key(k)
    except TagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return eq, present


@router.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    request: Request,
    source: str | None = Query(None),
    endpoint: str | None = Query(None),
    cwd: str | None = Query(None),
    tag: list[str] = Query(default_factory=list),
    since: str | None = Query(None),
    until: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    since_iso = _parse_iso(since, field="since")
    until_iso = _parse_iso(until, field="until")
    if since_iso and until_iso and since_iso > until_iso:
        raise HTTPException(
            status_code=400, detail="'since' must be <= 'until'",
        )
    tag_eq, tag_present = _split_tags(tag)

    total, rows = await request.app.state.db.sessions.list_sessions(
        source=source,
        endpoint=endpoint,
        cwd_prefix=cwd,
        tag_eq=tag_eq,
        tag_present=tag_present,
        since=since_iso,
        until=until_iso,
        limit=limit,
    )

    sessions = [
        SessionMeta(
            session_id=r["session_id"],
            source=r["source"],
            endpoint=f"{r['source']}@{r.get('location_label') or r.get('location') or ''}",
            location=r.get("location") or "",
            location_label=r.get("location_label"),
            cwd=r.get("cwd"),
            created_at=r["created_at"],
            synced_at=r["synced_at"],
            round_count=r.get("round_count") or 0,
            tags=r.get("tags") or {},
        )
        for r in rows
    ]
    return SessionListResponse(
        total=total, returned=len(sessions), sessions=sessions,
    )


@router.patch("/sessions/{session_id}/tags", response_model=TagResponse)
async def patch_session_tags(
    session_id: str, payload: TagPatchRequest, request: Request,
):
    """Set / unset / query tags. Empty body = query (returns current
    tags unchanged). Validates *before* any write so a partial failure
    can't leak a half-merged state to disk."""
    store = request.app.state.db.sessions
    current = await store.get_tags(session_id)
    if current is None:
        raise HTTPException(
            status_code=404, detail=f"session {session_id!r} not found",
        )

    try:
        merged = apply_patch(current, payload.set, payload.unset)
    except TagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Skip the UPDATE on no-op queries — saves a write + commit when
    # callers use empty PATCH bodies just to read.
    if payload.set or payload.unset:
        ok = await store.replace_tags(session_id, merged)
        if not ok:
            # Race: row vanished between get_tags + replace_tags. Tell
            # the client to retry.
            raise HTTPException(
                status_code=404, detail=f"session {session_id!r} not found",
            )
    return TagResponse(session_id=session_id, tags=merged)
