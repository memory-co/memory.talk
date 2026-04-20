from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from memory_talk.dsl import DSLError


class SearchRequest(BaseModel):
    query: str
    where: Optional[str] = None
    top_k: int = 10


router = APIRouter()


@router.post("/search")
def search(body: SearchRequest, request: Request):
    from memory_talk.service.search import SearchService

    svc = SearchService(request.app.state.config)
    try:
        return svc.search(body.query, where=body.where, top_k=body.top_k)
    except DSLError as e:
        raise HTTPException(status_code=400, detail=f"DSL parse error: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
