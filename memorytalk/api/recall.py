"""POST /v3/recall."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import RecallRequest, RecallResponse
from memorytalk.service import RecallServiceError


router = APIRouter()


@router.post("/recall", response_model=RecallResponse)
async def post_recall(payload: RecallRequest, request: Request) -> RecallResponse:
    svc = request.app.state.recall
    if svc is None:
        raise HTTPException(status_code=503, detail="recall service unavailable")
    try:
        result = await svc.recall(
            session_id=payload.session_id,
            prompt=payload.prompt,
            top_k=payload.top_k,
        )
    except RecallServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RecallResponse(**result)
