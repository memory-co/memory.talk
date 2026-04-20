from __future__ import annotations
from fastapi import APIRouter, Request, Query
from memory_talk.models.session import Session
from memory_talk.service.sessions import SessionsService

router = APIRouter()

@router.post("/sessions")
def create_session(session: Session, request: Request):
    svc = SessionsService(request.app.state.config)
    return svc.import_session(session)

@router.get("/sessions")
def list_sessions(request: Request, tag: str | None = Query(None)):
    svc = SessionsService(request.app.state.config)
    return svc.list_sessions(tag=tag)

@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request, start: int | None = Query(None), end: int | None = Query(None)):
    svc = SessionsService(request.app.state.config)
    return svc.get_session(session_id, start=start, end=end)

@router.post("/sessions/{session_id}/tags")
def add_tags(session_id: str, request: Request, body: dict):
    svc = SessionsService(request.app.state.config)
    svc.add_tags(session_id, body.get("tags", []))
    return {"status": "ok"}

@router.delete("/sessions/{session_id}/tags")
def remove_tags(session_id: str, request: Request, body: dict):
    svc = SessionsService(request.app.state.config)
    svc.remove_tags(session_id, body.get("tags", []))
    return {"status": "ok"}
