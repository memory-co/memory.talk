"""POST /v2/view."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import ViewIn
from memory_talk_v2.service.view import ViewError, ViewNotFound, view


router = APIRouter()


@router.post("/view")
async def post_view(payload: ViewIn, request: Request):
    app = request.app
    try:
        return view(payload.id, config=app.state.config, db=app.state.db)
    except ViewNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ViewError as e:
        raise HTTPException(status_code=400, detail=str(e))
