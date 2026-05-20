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

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import (
    AppendRoundsRequest, AppendRoundsResponse,
    EnsureSessionRequest, EnsureSessionResponse,
)
from memorytalk.service import IngestServiceError


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
