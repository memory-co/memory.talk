"""POST /v3/cards."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import CreateCardRequest, CreateCardResponse
from memorytalk.service import CardConflict, CardServiceError


router = APIRouter()


@router.post("/cards", response_model=CreateCardResponse)
async def post_cards(payload: CreateCardRequest, request: Request) -> CreateCardResponse:
    svc = request.app.state.cards
    if svc is None:
        raise HTTPException(status_code=503, detail="cards service unavailable")
    try:
        card_id = await svc.create(payload)
    except CardConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CardServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateCardResponse(card_id=card_id)
