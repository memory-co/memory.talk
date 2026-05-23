"""POST /v3/search."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import SearchRequest, SearchResponse
from memorytalk.util.dsl import DSLError
from memorytalk.util.formula import FormulaError


router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def post_search(payload: SearchRequest, request: Request) -> SearchResponse:
    svc = request.app.state.search
    if svc is None:
        raise HTTPException(status_code=503, detail="search service unavailable")
    try:
        return await svc.search(
            query=payload.query or "",
            where=payload.where,
            top_k=payload.top_k,
            show_all=payload.show_all,
        )
    except DSLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FormulaError as e:
        raise HTTPException(status_code=500, detail=str(e))
