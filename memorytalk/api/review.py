"""GET /v2/review/list, GET /v2/review/detail/{session_id}.

Pure read-only: thin wrappers over RecallStore queries. No service-layer
class needed — review has no business logic, it's just SELECTs.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.schemas import ReviewDetailResponse, ReviewListResponse
from memorytalk.util.ids import prefix_session_id


router = APIRouter()


@router.get("/review/list", response_model=ReviewListResponse)
async def review_list(
    request: Request,
    limit: int = Query(100, gt=0, le=1000),
):
    rows = await request.app.state.db.recall.list_sessions(limit=limit)
    return ReviewListResponse(sessions=rows)


@router.get("/review/detail/{session_id}", response_model=ReviewDetailResponse)
async def review_detail(
    session_id: str,
    request: Request,
    limit: int = Query(50, gt=0, le=500),
):
    sid = prefix_session_id(session_id)
    detail = await request.app.state.db.recall.session_detail(sid, limit=limit)
    if detail is None:
        raise HTTPException(status_code=404, detail="session not found in recall log")
    return ReviewDetailResponse(**detail)
