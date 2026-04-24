"""POST /v2/tags/{add,remove} — dispatched to SessionService (tags belong to sessions)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import TagsIn, TagsOut
from memory_talk_v2.service import SessionNotFound, SessionServiceError


router = APIRouter()


@router.post("/tags/add", response_model=TagsOut)
async def post_tags_add(payload: TagsIn, request: Request):
    try:
        return request.app.state.sessions.add_tags(payload.model_dump())
    except SessionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tags/remove", response_model=TagsOut)
async def post_tags_remove(payload: TagsIn, request: Request):
    try:
        return request.app.state.sessions.remove_tags(payload.model_dump())
    except SessionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
