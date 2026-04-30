"""POST /v2/recall."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import RecallRequest, RecallResponse
from memorytalk.service.recall import RecallError


router = APIRouter()


@router.post("/recall", response_model=RecallResponse)
async def post_recall(payload: RecallRequest, request: Request):
    try:
        return await request.app.state.recall.recall(payload)
    except RecallError as e:
        raise HTTPException(status_code=400, detail=str(e))
