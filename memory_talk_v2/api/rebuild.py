"""POST /v2/rebuild."""
from __future__ import annotations

from fastapi import APIRouter, Request

from memory_talk_v2.service.rebuild import rebuild


router = APIRouter()


@router.post("/rebuild")
async def post_rebuild(request: Request) -> dict:
    app = request.app
    return rebuild(
        config=app.state.config,
        db=app.state.db,
        vectors=app.state.vectors,
        embedder=app.state.embedder,
    )
