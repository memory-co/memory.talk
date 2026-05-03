"""Tag endpoints — resource-rooted (subject in URL path).

Sessions:
  POST   /v2/sessions/{session_id}/tags   body: {"tags": ["k:v", ...]}
  DELETE /v2/sessions/{session_id}/tags?key=k1&key=k2

Cards (commit 2 will enable):
  POST   /v2/cards/{card_id}/tags
  DELETE /v2/cards/{card_id}/tags?key=...

Subject-id prefix validation happens inside TagService — the path param
just plumbs whatever string the URL had through. A wrong-prefix id
(e.g. ``sess_xxx`` posted to the cards route) returns 400 from the
service layer rather than a 404 from FastAPI routing.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.schemas import TagsAddRequest, TagsResponse
from memorytalk.service import SessionNotFound, TagServiceError


router = APIRouter()


async def _wrap_call(coro):
    try:
        return await coro
    except SessionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TagServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/tags", response_model=TagsResponse)
async def post_session_tags(
    session_id: str, payload: TagsAddRequest, request: Request,
) -> TagsResponse:
    return await _wrap_call(
        request.app.state.tags.add_tags(session_id, payload.tags)
    )


@router.delete("/sessions/{session_id}/tags", response_model=TagsResponse)
async def delete_session_tags(
    session_id: str, request: Request,
    key: list[str] = Query(..., min_length=1),
) -> TagsResponse:
    return await _wrap_call(
        request.app.state.tags.remove_tags(session_id, key)
    )


@router.post("/cards/{card_id}/tags", response_model=TagsResponse)
async def post_card_tags(
    card_id: str, payload: TagsAddRequest, request: Request,
) -> TagsResponse:
    return await _wrap_call(
        request.app.state.tags.add_tags(card_id, payload.tags)
    )


@router.delete("/cards/{card_id}/tags", response_model=TagsResponse)
async def delete_card_tags(
    card_id: str, request: Request,
    key: list[str] = Query(..., min_length=1),
) -> TagsResponse:
    return await _wrap_call(
        request.app.state.tags.remove_tags(card_id, key)
    )
