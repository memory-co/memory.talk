"""POST /v2/cards."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import CreateCardRequest, CreateCardResponse
from memorytalk.service import CardConflictError, CardServiceError


router = APIRouter()


@router.post("/cards", response_model=CreateCardResponse)
async def post_cards(payload: CreateCardRequest, request: Request):
    try:
        return await request.app.state.cards.create(payload)
    except CardConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CardServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
