"""POST /v3/recall + GET /v3/recall/sessions + GET /v3/recall/sessions/{sid}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.schemas import (
    RecallListResponse,
    RecallReadResponse,
    RecallRequest,
    RecallResponse,
)
from memorytalk.service import RecallServiceError


router = APIRouter()


@router.post("/recall", response_model=RecallResponse)
async def post_recall(payload: RecallRequest, request: Request) -> RecallResponse:
    """Hook entry point. Caller MUST supply ``source`` so the server
    can mint the canonical session_id correctly."""
    svc = request.app.state.recall
    if svc is None:
        raise HTTPException(status_code=503, detail="recall service unavailable")
    try:
        result = await svc.recall(
            source=payload.source,
            location=payload.location,
            raw_session_id=payload.session_id,
            prompt=payload.prompt,
            top_k=payload.top_k,
        )
    except RecallServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RecallResponse(**result)


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


@router.get(
    "/recall/sessions/{session_id}", response_model=RecallReadResponse,
)
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
        result = await svc.read_session(
            session_id, limit=limit, reverse=reverse,
        )
    except RecallServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RecallReadResponse(**result)
