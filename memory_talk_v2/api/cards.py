"""POST /v2/cards."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import CreateCardIn, CreateCardOut
from memory_talk_v2.service.cards import (
    CardConflictError, CardServiceError, create_card,
)
from memory_talk_v2.service.events import EventWriter


router = APIRouter()


@router.post("/cards", response_model=CreateCardOut)
async def post_cards(payload: CreateCardIn, request: Request):
    app = request.app
    events = EventWriter(app.state.config, app.state.db)
    try:
        result = create_card(
            payload.model_dump(),
            config=app.state.config,
            db=app.state.db,
            vectors=app.state.vectors,
            embedder=app.state.embedder,
            events=events,
        )
    except CardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CardServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
