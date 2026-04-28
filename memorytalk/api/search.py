"""POST /v2/search."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import SearchRequest, SearchResponse
from memorytalk.service import SearchError


router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def post_search(payload: SearchRequest, request: Request):
    try:
        return await request.app.state.search.search(payload)
    except SearchError as e:
        raise HTTPException(status_code=400, detail=str(e))
