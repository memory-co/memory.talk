"""/v4 cards — create / list card, add / list positions, link, sessions."""
from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.api._card_common import http_from_service_error, require
from memorytalk.schemas.card_requests import (
    CreateCardRequest, CreateCardResponse, CreateLinkRequest, CreateLinkResponse,
    CreatePositionRequest, CreatePositionResponse,
)
from memorytalk.service.cards import CardServiceError
from memorytalk.service.credence import credence, sort_key, with_credence

router = APIRouter()


def _parse_iso(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    try:
        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"invalid ISO 8601 in '{field}': {value!r}")
    return value


@router.post("/cards", response_model=CreateCardResponse)
async def post_card(payload: CreateCardRequest, request: Request) -> CreateCardResponse:
    svc = require(request.app.state.cards, "cards")
    try:
        card_id = await svc.create_card(payload)
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreateCardResponse(card_id=card_id)


@router.get("/cards")
async def get_cards(
    request: Request,
    since: str | None = Query(None),
    until: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    db = request.app.state.db
    since_iso = _parse_iso(since, field="since")
    until_iso = _parse_iso(until, field="until")
    if since_iso and until_iso and since_iso > until_iso:
        raise HTTPException(status_code=400, detail="'since' must be <= 'until'")
    total, rows = await db.cards.list_cards(since=since_iso, until=until_iso, limit=limit)
    return {"total": total, "returned": len(rows), "cards": rows}


@router.post("/cards/{card_id}/positions", response_model=CreatePositionResponse)
async def post_position(card_id: str, payload: CreatePositionRequest, request: Request) -> CreatePositionResponse:
    svc = require(request.app.state.cards, "cards")
    try:
        position = await svc.add_position(card_id, payload)
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreatePositionResponse(card_id=card_id, position=position)


@router.get("/cards/{card_id}/positions")
async def get_positions(card_id: str, request: Request):
    db = request.app.state.db
    card = await db.cards.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"card {card_id} not found")
    rows = await db.positions.list_for_card(card_id)
    injected = []
    for r in rows:
        reviews = await db.reviews.list_for_target(card_id, r["position"])
        inj = with_credence(r, reviews[0]["created_at"] if reviews else None)
        inj["id"] = f"{card_id}#{r['position']}"
        injected.append(inj)
    injected.sort(key=sort_key, reverse=True)
    return {"card_id": card_id, "issue": card["issue"], "positions": injected}


@router.post("/cards/{card_id}/links", response_model=CreateLinkResponse)
async def post_link(card_id: str, payload: CreateLinkRequest, request: Request) -> CreateLinkResponse:
    svc = require(request.app.state.cards, "cards")
    # path card_id is authoritative
    payload = payload.model_copy(update={"card_id": card_id})
    try:
        result = await svc.link(card_id, payload)
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreateLinkResponse(**result)


@router.get("/cards/{card_id}/links")
async def get_links(card_id: str, request: Request):
    db = request.app.state.db
    if not await db.cards.exists(card_id):
        raise HTTPException(status_code=404, detail=f"card {card_id} not found")
    rows = await db.card_links.list_out(card_id)
    links = [
        {**e, "id": f"{card_id}#{e['link']}",
         "credence": credence(e["up_count"], e["down_count"])}
        for e in rows
    ]
    return {"card_id": card_id, "links": links}


@router.get("/cards/{card_id}/sessions")
async def get_card_sessions(card_id: str, request: Request):
    db = request.app.state.db
    if not await db.cards.exists(card_id):
        raise HTTPException(status_code=404, detail=f"card {card_id} not found")
    return {"card_id": card_id, "sessions": await db.card_sessions.list_for_card(card_id)}
