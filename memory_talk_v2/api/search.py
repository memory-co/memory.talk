"""POST /v2/search."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memory_talk_v2.models import SearchIn
from memory_talk_v2.service.search import SearchError, search


router = APIRouter()


@router.post("/search")
async def post_search(payload: SearchIn, request: Request):
    app = request.app
    try:
        return search(
            payload.model_dump(),
            config=app.state.config,
            db=app.state.db,
            vectors=app.state.vectors,
            embedder=app.state.embedder,
            search_jsonl=app.state.search_jsonl,
        )
    except SearchError as e:
        raise HTTPException(status_code=400, detail=str(e))
