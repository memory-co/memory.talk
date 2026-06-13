"""POST /v3/explores + GET /v3/explores + GET /v3/explores/{eid}.

Plural ``/v3/explores`` is the explore *object* surface (create / view /
list), deliberately distinct from the legacy ``/v3/explore/*`` cwd feed.
Card/review minting under an explore goes through the existing
``/v3/cards`` / ``/v3/reviews`` endpoints with an ``explore_id``.
"""
from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.service.explores import ExploreServiceError


router = APIRouter()


class CreateExploreRequest(BaseModel):
    entrypoint_session_id: str | None = None
    divider_at: str | None = None
    note: str | None = None


@router.post("/explores")
async def post_explores(payload: CreateExploreRequest, request: Request) -> dict:
    svc = request.app.state.explore
    try:
        explore_id = await svc.create(
            entrypoint_session_id=payload.entrypoint_session_id,
            divider_at=payload.divider_at,
            note=payload.note,
        )
    except ExploreServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    row = await request.app.state.db.explores.get(explore_id)
    part = await svc.get_partition(explore_id)
    return {
        "explore_id": explore_id,
        "divider_at": row["divider_at"],
        "dir_path": row["dir_path"],
        "prior_count": len(part["prior"]),
        "posterior_count": len(part["posterior"]),
    }


@router.get("/explores")
async def list_explores(request: Request, limit: int = Query(50, ge=1, le=200)) -> dict:
    rows = await request.app.state.db.explores.list(limit=limit)
    return {"explores": rows}


@router.get("/explores/{explore_id}")
async def get_explore(explore_id: str, request: Request) -> dict:
    row = await request.app.state.db.explores.get(explore_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"explore {explore_id} not found")
    part = await request.app.state.explore.get_partition(explore_id)
    return {**row, "prior": part["prior"], "posterior": part["posterior"]}
