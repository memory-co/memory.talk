"""/v4 positions — review a Position (argument ±1/0)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from memorytalk.api._card_common import http_from_service_error, require
from memorytalk.schemas.card_requests import CreateReviewRequest, CreateReviewResponse
from memorytalk.service.cards import CardServiceError

router = APIRouter()


@router.post("/positions/{position_id}/reviews", response_model=CreateReviewResponse)
async def post_review(position_id: str, payload: CreateReviewRequest, request: Request) -> CreateReviewResponse:
    svc = require(request.app.state.cards, "cards")
    # path position_id is authoritative
    payload = payload.model_copy(update={"position_id": position_id})
    try:
        result = await svc.review(position_id, payload)
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreateReviewResponse(
        review_id=result["review_id"], position_id=result["position_id"],
        argument=result["argument"],
    )
