"""POST /v2/links."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import CreateLinkIn, CreateLinkOut
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.links import (
    LinkNotFoundError, LinkServiceError, create_user_link,
)


router = APIRouter()


@router.post("/links", response_model=CreateLinkOut)
async def post_links(payload: CreateLinkIn, request: Request):
    app = request.app
    events = EventWriter(app.state.config, app.state.db)
    try:
        result = create_user_link(
            payload.model_dump(),
            config=app.state.config,
            db=app.state.db,
            events=events,
        )
    except LinkNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LinkServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
