"""/v4 cards — create / list card, add / list positions, link, sessions."""
from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.api.v4._common import http_from_service_error, require
from memorytalk.schemas.v4.requests import (
    CreateCardRequest, CreateCardResponse, CreateCardSessionRequest,
    CreateCardSessionResponse, CreateLinkRequest, CreateLinkResponse,
    CreatePositionRequest, CreatePositionResponse,
)
from memorytalk.service.cards import CardServiceError
from memorytalk.service.v4_credence import sort_key, with_credence

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
    total, rows = await db.v4cards.list_cards(since=since_iso, until=until_iso, limit=limit)
    return {"total": total, "returned": len(rows), "cards": rows}


@router.post("/cards/{card_id}/positions", response_model=CreatePositionResponse)
async def post_position(card_id: str, payload: CreatePositionRequest, request: Request) -> CreatePositionResponse:
    svc = require(request.app.state.cards, "cards")
    try:
        position_id = await svc.add_position(card_id, payload)
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreatePositionResponse(card_id=card_id, position_id=position_id)


@router.get("/cards/{card_id}/positions")
async def get_positions(card_id: str, request: Request):
    db = request.app.state.db
    card = await db.v4cards.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"card {card_id} not found")
    rows = await db.positions.list_for_card(card_id)
    injected = []
    for r in rows:
        reviews = await db.v4reviews.list_for_position(r["position_id"])
        injected.append(with_credence(r, reviews[0]["created_at"] if reviews else None))
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


@router.post("/cards/{card_id}/sessions", response_model=CreateCardSessionResponse)
async def post_card_session(card_id: str, payload: CreateCardSessionRequest, request: Request) -> CreateCardSessionResponse:
    svc = require(request.app.state.cards, "cards")
    try:
        result = await svc.add_session(
            card_id, payload.session_id, payload.position_id, payload.indexes,
        )
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreateCardSessionResponse(**result)


@router.get("/cards/{card_id}/sessions")
async def get_card_sessions(card_id: str, request: Request):
    db = request.app.state.db
    if not await db.v4cards.exists(card_id):
        raise HTTPException(status_code=404, detail=f"card {card_id} not found")
    return {"card_id": card_id, "sessions": await db.card_sessions.list_for_card(card_id)}
