"""Recall endpoints under /v4.

POST /v4/recall                      — v4 card recall (collide on issue →
                                       current answer + scope), deduped per
                                       session against recall history.
GET  /v4/recall/sessions             — sessions with any recall history.
GET  /v4/recall/sessions/{sid}       — one session's recall timeline.

The list/read endpoints read the shared ``recall_event`` log (the same log
the card recall writes to), so they inspect card-recall history.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.api._card_common import http_from_service_error, require
from memorytalk.schemas import RecallListResponse, RecallReadResponse
from memorytalk.schemas.card_requests import V4RecallRequest
from memorytalk.service import RecallServiceError
from memorytalk.service.cards import CardServiceError

router = APIRouter()


@router.post("/recall")
async def post_recall(payload: V4RecallRequest, request: Request):
    """Card recall. Caller supplies the canonical ``session_id`` (the hook
    mints it client-side via the adapter)."""
    svc = require(request.app.state.v4recall, "recall")
    try:
        return await svc.recall(payload.session_id, payload.prompt, top_k=payload.top_k)
    except CardServiceError as e:
        raise http_from_service_error(e)


@router.get("/recall/sessions", response_model=RecallListResponse)
async def list_recall_sessions(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
) -> RecallListResponse:
    """All sessions that have any recall history, most-recent first."""
    svc = request.app.state.recall
    if svc is None:
        raise HTTPException(status_code=503, detail="recall service unavailable")
    try:
        result = await svc.list_sessions(limit=limit)
    except RecallServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RecallListResponse(**result)


@router.get("/recall/sessions/{session_id}", response_model=RecallReadResponse)
async def read_recall_session(
    session_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    reverse: bool = Query(False),
) -> RecallReadResponse:
    """Timeline of recall events for one session."""
    svc = request.app.state.recall
    if svc is None:
        raise HTTPException(status_code=503, detail="recall service unavailable")
    try:
        result = await svc.read_session(session_id, limit=limit, reverse=reverse)
    except RecallServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RecallReadResponse(**result)
