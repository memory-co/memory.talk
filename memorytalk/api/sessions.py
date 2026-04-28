"""POST /v2/sessions — ingest."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import IngestSessionRequest, IngestSessionResponse
from memorytalk.service import SessionServiceError


router = APIRouter()


@router.post("/sessions", response_model=IngestSessionResponse)
async def post_sessions(payload: IngestSessionRequest, request: Request):
    try:
        return await request.app.state.sessions.ingest(payload)
    except SessionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
