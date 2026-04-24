"""POST /v2/sessions — ingest."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.schemas import IngestSessionRequest, IngestSessionResponse
from memory_talk_v2.service import SessionServiceError


router = APIRouter()


@router.post("/sessions", response_model=IngestSessionResponse)
async def post_sessions(payload: IngestSessionRequest, request: Request):
    try:
        return await request.app.state.sessions.ingest(payload)
    except SessionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
