"""POST /v2/links."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.schemas import CreateLinkRequest, CreateLinkResponse
from memorytalk.service import LinkNotFoundError, LinkServiceError


router = APIRouter()


@router.post("/links", response_model=CreateLinkResponse)
async def post_links(payload: CreateLinkRequest, request: Request):
    try:
        return await request.app.state.links.create(payload)
    except LinkNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LinkServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
