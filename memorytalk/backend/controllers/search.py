"""/api/search —— 综合搜索:一个 q,工作 / 元认知 / 成员各出一份命中。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from memorytalk.backend.models.result import Result, ok
from memorytalk.backend.models.search import SearchResult
from memorytalk.backend.services.search import SearchService

router = APIRouter(prefix="/api/search", tags=["search"])


def search_service(request: Request) -> SearchService:
    return request.app.state.search


@router.get("", response_model=Result[SearchResult], summary="综合搜索:工作(目标)、元认知(git grep 全文)、成员(名字 / 邮箱);每种最多 limit 条")
def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100), svc: SearchService = Depends(search_service)):
    return ok(svc.search(q, limit))
