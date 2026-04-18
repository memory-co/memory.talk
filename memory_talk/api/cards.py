from __future__ import annotations
from fastapi import APIRouter, Request, Query, HTTPException
from memory_talk.service.cards import CardsService

router = APIRouter()

@router.post("/cards")
def create_card(body: dict, request: Request):
    svc = CardsService(request.app.state.config)
    return svc.create(body)

@router.get("/cards")
def list_cards(request: Request, session_id: str | None = Query(None)):
    svc = CardsService(request.app.state.config)
    return svc.list_cards(session_id=session_id)

@router.get("/cards/{card_id}")
def get_card(card_id: str, request: Request, link_id: str | None = Query(None)):
    svc = CardsService(request.app.state.config)
    result = svc.get(card_id, link_id=link_id)
    if result is None:
        raise HTTPException(404, "Card not found")
    return result
