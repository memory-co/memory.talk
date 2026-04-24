"""POST /v2/view — prefix-dispatched read."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.ids import IdKind, InvalidIdError, parse_id
from memory_talk_v2.models import ViewIn
from memory_talk_v2.service import (
    CardNotFound, CardServiceError, SessionNotFound, SessionServiceError,
)


router = APIRouter()


@router.post("/view")
async def post_view(payload: ViewIn, request: Request):
    try:
        kind, _ = parse_id(payload.id)
    except InvalidIdError:
        raise HTTPException(status_code=400, detail="invalid id prefix")

    try:
        if kind == IdKind.CARD:
            return await request.app.state.cards.view(payload.id)
        if kind == IdKind.SESSION:
            return await request.app.state.sessions.view(payload.id)
    except (CardNotFound, SessionNotFound) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (CardServiceError, SessionServiceError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    raise HTTPException(status_code=400, detail="invalid id prefix")
