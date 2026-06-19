"""POST /v4/read — prefix-dispatched read.

Single entry point that routes by id prefix:
  card_    → v4 card (issue + positions + credence + links + provenance)
  pos_     → v4 position (claim + reviews)
  insight_ → read-only old card (the renamed v3 "card"; view only)
  sess-    → session (rounds from jsonl)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.api._card_common import require
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

    if kind == IdKind.CARD:
        svc = require(request.app.state.v4read, "read")
        card = await svc.read_card(payload.id)
        if card is None:
            raise HTTPException(status_code=404, detail=f"card {payload.id} not found")
        return {"type": "card", "card": card}

    if kind == IdKind.POSITION:
        svc = require(request.app.state.v4read, "read")
        pos = await svc.read_position(payload.id)
        if pos is None:
            raise HTTPException(status_code=404, detail=f"position {payload.id} not found")
        return {"type": "position", "position": pos}

    if kind == IdKind.INSIGHT:
        # read-only old card (renamed v3 card). View only.
        svc = require(request.app.state.read, "read")
        try:
            insight, read_at = await svc.read_insight(payload.id)
        except InsightNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"type": "insight", "read_at": read_at, "insight": insight.model_dump()}

    if kind == IdKind.SESSION:
        svc = require(request.app.state.read, "read")
        try:
            session, read_at = await svc.read_session(payload.id)
        except SessionNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"type": "session", "read_at": read_at, "session": session.model_dump()}

    raise HTTPException(status_code=400, detail="invalid id prefix")
