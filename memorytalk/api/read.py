"""POST /v4/read — prefix/fragment-dispatched read.

Single entry point that routes by id:
  card_              → v4 card (issue + positions + credence + links + provenance)
  card_…#p<n>        → v4 position (claim + reviews + credence)
  card_…#l<n>        → v4 link (claim + reviews + credence)
  insight_           → read-only old card (the renamed v3 "card"; view only)
  sess- / sess_      → session (rounds from jsonl)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.api._card_common import require
from memorytalk.schemas import ReadRequest
from memorytalk.service import InsightNotFound, SessionNotFound
from memorytalk.util.ids import IdKind, InvalidIdError, parse_fragment

router = APIRouter()


@router.post("/read")
async def post_read(payload: ReadRequest, request: Request):
    try:
        base_id, kind, seq = parse_fragment(payload.id)
    except InvalidIdError:
        raise HTTPException(status_code=400, detail="invalid id prefix")

    if kind == IdKind.POSITION:
        svc = require(request.app.state.v4read, "read")
        pos = await svc.read_position(base_id, seq)
        if pos is None:
            raise HTTPException(status_code=404, detail=f"position {payload.id} not found")
        return {"type": "position", "position": pos}

    if kind == IdKind.MARK:
        # sess_…#m<n> → the mark's canonical YAML (description / last_index /
        # mark text / indexes? / issues / created_at).
        svc = require(getattr(request.app.state, "session_marks", None), "session marks")
        mark = await svc.read_mark(base_id, seq)
        if mark is None:
            raise HTTPException(status_code=404, detail=f"mark {payload.id} not found")
        return {"type": "mark", "mark": mark}

    if kind == IdKind.LINK:
        svc = require(request.app.state.v4read, "read")
        ln = await svc.read_link(base_id, seq)
        if ln is None:
            raise HTTPException(status_code=404, detail=f"link {payload.id} not found")
        return {"type": "link", "link": ln}

    if kind == IdKind.CARD:
        svc = require(request.app.state.v4read, "read")
        card = await svc.read_card(payload.id)
        if card is None:
            raise HTTPException(status_code=404, detail=f"card {payload.id} not found")
        return {"type": "card", "card": card}

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
