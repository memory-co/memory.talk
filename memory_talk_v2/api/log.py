"""POST /v2/log — prefix-dispatched event stream."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.ids import IdKind, InvalidIdError, parse_id
from memory_talk_v2.models import LogIn
from memory_talk_v2.service import (
    CardNotFound, CardServiceError, SessionNotFound, SessionServiceError,
)


router = APIRouter()


@router.post("/log")
async def post_log(payload: LogIn, request: Request):
    try:
        kind, _ = parse_id(payload.id)
    except InvalidIdError:
        raise HTTPException(status_code=400, detail="invalid id prefix")

    try:
        if kind == IdKind.CARD:
            return request.app.state.cards.log(payload.id)
        if kind == IdKind.SESSION:
            return request.app.state.sessions.log(payload.id)
    except (CardNotFound, SessionNotFound) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (CardServiceError, SessionServiceError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    raise HTTPException(status_code=400, detail="invalid id prefix")
