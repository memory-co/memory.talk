"""POST /v2/rebuild."""
from __future__ import annotations

from fastapi import APIRouter, Request

from memory_talk_v2.schemas import RebuildResponse


router = APIRouter()


@router.post("/rebuild", response_model=RebuildResponse)
async def post_rebuild(request: Request):
    return await request.app.state.rebuild.rebuild()
