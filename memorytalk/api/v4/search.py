"""/v4 search — collide-on-issue retrieval + where DSL over current answer."""
from __future__ import annotations

from fastapi import APIRouter, Request

from memorytalk.api.v4._common import http_from_service_error, require
from memorytalk.schemas.v4.requests import V4SearchRequest
from memorytalk.service.cards import CardServiceError

router = APIRouter()


@router.post("/search")
async def post_search(payload: V4SearchRequest, request: Request):
    svc = require(request.app.state.v4search, "search")
    try:
        return await svc.search(payload.query, payload.where, payload.limit)
    except CardServiceError as e:
        raise http_from_service_error(e)
