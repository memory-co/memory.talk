"""/v4 recall — unconscious recall: collide on issue → answer + scope."""
from __future__ import annotations

from fastapi import APIRouter, Request

from memorytalk.api.v4._common import http_from_service_error, require
from memorytalk.schemas.v4.requests import V4RecallRequest
from memorytalk.service.cards import CardServiceError

router = APIRouter()


@router.post("/recall")
async def post_recall(payload: V4RecallRequest, request: Request):
    svc = require(request.app.state.v4recall, "recall")
    try:
        return await svc.recall(payload.session_id, payload.prompt, top_k=payload.top_k)
    except CardServiceError as e:
        raise http_from_service_error(e)
