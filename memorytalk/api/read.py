"""POST /v3/read — prefix-dispatched read of card or session."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import ReadRequest
from memorytalk.service import InsightNotFound, SessionNotFound
from memorytalk.util.ids import IdKind, InvalidIdError, parse_id


router = APIRouter()


@router.post("/read")
async def post_read(payload: ReadRequest, request: Request):
    try:
        kind, _ = parse_id(payload.id)
    except InvalidIdError:
        raise HTTPException(status_code=400, detail="invalid id prefix")

    svc = request.app.state.read

    try:
        if kind == IdKind.CARD:
            card, read_at = await svc.read_insight(payload.id)
            return {"type": "card", "read_at": read_at, "card": card.model_dump()}
        if kind == IdKind.SESSION:
            session, read_at = await svc.read_session(payload.id)
            return {"type": "session", "read_at": read_at,
                    "session": session.model_dump()}
    except InsightNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    raise HTTPException(status_code=400, detail="invalid id prefix")
