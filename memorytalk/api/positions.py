"""/v4 reviews — review a Position OR a CardLink (argument ±1/0).

A review targets an addressed subordinate: ``card_id#p<n>`` (position) or
``card_id#l<n>`` (link). Both edges and answers are governed objects, so
both are reviewable; the service derives ``target_kind`` from the seq.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from memorytalk.api._card_common import http_from_service_error, require
from memorytalk.schemas.card_requests import CreateReviewRequest, CreateReviewResponse
from memorytalk.service.cards import CardServiceError

router = APIRouter()


@router.post("/cards/{card_id}/positions/{position}/reviews",
             response_model=CreateReviewResponse)
async def post_position_review(
    card_id: str, position: str, payload: CreateReviewRequest, request: Request,
) -> CreateReviewResponse:
    svc = require(request.app.state.cards, "cards")
    target = f"{card_id}#{position}"
    try:
        result = await svc.review(target, payload)
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreateReviewResponse(
        review_id=result["review_id"], target=result["target"],
        target_kind=result["target_kind"], argument=result["argument"],
    )


@router.post("/cards/{card_id}/links/{link}/reviews",
             response_model=CreateReviewResponse)
async def post_link_review(
    card_id: str, link: str, payload: CreateReviewRequest, request: Request,
) -> CreateReviewResponse:
    svc = require(request.app.state.cards, "cards")
    target = f"{card_id}#{link}"
    try:
        result = await svc.review(target, payload)
    except CardServiceError as e:
        raise http_from_service_error(e)
    return CreateReviewResponse(
        review_id=result["review_id"], target=result["target"],
        target_kind=result["target_kind"], argument=result["argument"],
    )
