"""POST /v2/log."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import LogIn
from memory_talk_v2.service.log import LogError, LogNotFound, log


router = APIRouter()


@router.post("/log")
async def post_log(payload: LogIn, request: Request):
    app = request.app
    try:
        return log(payload.id, config=app.state.config, db=app.state.db)
    except LogNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LogError as e:
        raise HTTPException(status_code=400, detail=str(e))
