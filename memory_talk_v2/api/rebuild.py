"""POST /v2/rebuild."""
from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.post("/rebuild")
async def post_rebuild(request: Request) -> dict:
    return request.app.state.rebuild.rebuild()
