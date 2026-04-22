"""POST /v2/tags/{add,remove}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import TagsIn, TagsOut
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.tags import (
    TagNotFoundError, TagServiceError, add_tags, remove_tags,
)


router = APIRouter()


@router.post("/tags/add", response_model=TagsOut)
async def post_tags_add(payload: TagsIn, request: Request):
    app = request.app
    events = EventWriter(app.state.event_jsonl, app.state.db)
    try:
        return add_tags(
            payload.model_dump(),
            db=app.state.db,
            events=events,
            sessions_root=app.state.config.sessions_dir,
        )
    except TagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TagServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tags/remove", response_model=TagsOut)
async def post_tags_remove(payload: TagsIn, request: Request):
    app = request.app
    events = EventWriter(app.state.event_jsonl, app.state.db)
    try:
        return remove_tags(
            payload.model_dump(),
            db=app.state.db,
            events=events,
            sessions_root=app.state.config.sessions_dir,
        )
    except TagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TagServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
