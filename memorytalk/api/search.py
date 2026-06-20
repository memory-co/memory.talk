"""POST /v4/search — unified semantic search.

A single relevance-ranked stream over the three memories: v4 cards
(issue + current answer), migrated insights, and session rounds. Each
result is tagged by ``kind``. The optional ``where`` DSL filters only the
card results' current answer; insight / session hits pass through by
relevance. See ``service/card_search.py::V4SearchService``.
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
