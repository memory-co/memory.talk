"""POST /v3/reviews."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import CreateReviewRequest, CreateReviewResponse
from memorytalk.service import ReviewConflict, ReviewServiceError


router = APIRouter()


@router.post("/reviews", response_model=CreateReviewResponse)
async def post_reviews(
    payload: CreateReviewRequest, request: Request,
) -> CreateReviewResponse:
    svc = request.app.state.reviews
    if svc is None:
        raise HTTPException(status_code=503, detail="reviews service unavailable")
    try:
        result = await svc.create(payload)
    except ReviewConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReviewServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateReviewResponse(**result)
