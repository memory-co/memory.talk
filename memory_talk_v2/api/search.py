"""POST /v2/search."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.schemas import SearchIn
from memory_talk_v2.service import SearchError


router = APIRouter()


@router.post("/search")
async def post_search(payload: SearchIn, request: Request):
    try:
        return await request.app.state.search.search(payload.model_dump())
    except SearchError as e:
        raise HTTPException(status_code=400, detail=str(e))
