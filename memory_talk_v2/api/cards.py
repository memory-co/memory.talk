"""POST /v2/cards."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.schemas import CreateCardIn, CreateCardOut
from memory_talk_v2.service import CardConflictError, CardServiceError


router = APIRouter()


@router.post("/cards", response_model=CreateCardOut)
async def post_cards(payload: CreateCardIn, request: Request):
    try:
        return await request.app.state.cards.create(payload.model_dump())
    except CardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CardServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
