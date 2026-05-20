"""POST /v3/sessions — legacy whole-session ingest entry point.

Internally translates to the cursor-based ``ensure_session`` +
``append_rounds`` protocol that ``SyncWatcher`` and any future remote
ingest pipeline use. Kept as a convenient external entry point (and to
keep historical tests that wrote sessions through this route working).

Semantics:

  - Look up the server's current ``last_round_id`` for this session.
  - If it's None (new session): append every input round.
  - If it points at round X: include only the rounds that come AFTER X
    in the input list. The pre-X rounds are assumed to be unchanged
    (same round_id ⇒ same content under our append-only model).
  - If X isn't in the input list at all (stale / divergent payload):
    nothing is appended; surface as ``action="skipped"``.

The legacy fields ``sha256`` and ``partial_append`` / ``overwrite_skipped``
are no longer meaningful — we don't track content-hash overwrites at the
round level any more. ``sha256`` is accepted and ignored;
``overwrite_skipped`` is always ``[]`` in the response.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import (
    AppendRoundsRequest, EnsureSessionRequest,
    IngestSessionRequest, IngestSessionResponse,
)
from memorytalk.service import IngestServiceError


router = APIRouter()


@router.post("/sessions", response_model=IngestSessionResponse)
async def post_sessions(payload: IngestSessionRequest, request: Request):
    ingest = request.app.state.ingest
    try:
        ensure = await ingest.ensure_session(EnsureSessionRequest(
            source=payload.source, session_id=payload.session_id,
        ))
    except IngestServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))

    server_last = ensure.last_round_id

    # Filter the incoming payload to "rounds that come after server_last".
    if server_last is None:
        new_rounds = list(payload.rounds)
    else:
        new_rounds = []
        seen_marker = False
        for r in payload.rounds:
            if not seen_marker:
                if r.round_id == server_last:
                    seen_marker = True
                continue
            new_rounds.append(r)
        if not seen_marker:
            new_rounds = []  # marker not found — divergent payload, ignore

    try:
        result = await ingest.append_rounds(AppendRoundsRequest(
            session_id=payload.session_id,
            source=payload.source,
            expected_prev_round_id=server_last,
            rounds=new_rounds,
            created_at=payload.created_at,
            metadata=payload.metadata,
        ))
    except IngestServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result.status == "conflict":
        # Shouldn't happen — we just read the cursor and used it. If it
        # does, the only honest answer is 409.
        raise HTTPException(
            status_code=409,
            detail=f"cursor moved mid-request: actual={result.actual_last_round_id}",
        )

    if result.appended_count > 0:
        action = "imported" if server_last is None else "appended"
    else:
        action = "skipped"

    return IngestSessionResponse(
        status="ok",
        session_id=result.session_id,
        action=action,
        round_count=result.round_count,
        added_count=result.appended_count,
        overwrite_skipped=[],
    )
