"""POST /v2/tags/{add,remove}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import TagsRequest, TagsResponse
from memorytalk.service import SessionNotFound, SessionServiceError


router = APIRouter()


@router.post("/tags/add", response_model=TagsResponse)
async def post_tags_add(payload: TagsRequest, request: Request):
    try:
        return await request.app.state.sessions.add_tags(payload)
    except SessionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tags/remove", response_model=TagsResponse)
async def post_tags_remove(payload: TagsRequest, request: Request):
    try:
        return await request.app.state.sessions.remove_tags(payload)
    except SessionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
