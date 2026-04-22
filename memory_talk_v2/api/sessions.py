"""POST /v2/sessions — ingest."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import IngestSessionIn, IngestSessionOut
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.sessions import ingest_session, SessionServiceError


router = APIRouter()


@router.post("/sessions", response_model=IngestSessionOut)
async def post_sessions(payload: IngestSessionIn, request: Request):
    app = request.app
    events = EventWriter(app.state.event_jsonl, app.state.db)
    try:
        result = ingest_session(
            payload.model_dump(),
            db=app.state.db,
            vectors=app.state.vectors,
            events=events,
            sessions_root=app.state.config.sessions_dir,
        )
    except SessionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
