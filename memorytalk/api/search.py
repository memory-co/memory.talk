"""POST /v4/search — v4 card search.

Collide on issue, return each card's current answer; the optional
``where`` DSL filters over that current answer.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from memorytalk.api._card_common import http_from_service_error, require
from memorytalk.schemas.card_requests import V4SearchRequest
from memorytalk.service.cards import CardServiceError

router = APIRouter()


@router.post("/search")
async def post_search(payload: V4SearchRequest, request: Request):
    svc = require(request.app.state.v4search, "search")
    try:
        return await svc.search(payload.query, payload.where, payload.limit)
    except CardServiceError as e:
        raise http_from_service_error(e)
