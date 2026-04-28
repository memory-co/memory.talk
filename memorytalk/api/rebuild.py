"""POST /v2/rebuild."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import RebuildResponse


router = APIRouter()


@router.post("/rebuild", response_model=RebuildResponse)
async def post_rebuild(request: Request):
    app = request.app
    if getattr(app.state, "status", "running") != "running":
        raise HTTPException(status_code=409, detail="rebuild already in progress")
    app.state.status = "rebuilding"
    try:
        return await app.state.rebuild.rebuild()
    finally:
        app.state.status = "running"
