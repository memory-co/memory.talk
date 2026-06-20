"""/v4 session marks — submit a batch of marks; list a session's marks.

  POST /v4/sessions/{session_id}/marks   submit (optimistic-locked)
  GET  /v4/sessions/{session_id}/marks   list metadata (from session_marks)

Reading one mark's body goes through ``POST /v4/read`` (``sess_…#m<n>``,
dispatched in ``api/read.py``).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.api._card_common import require
from memorytalk.schemas.card_requests import SubmitMarksRequest
from memorytalk.service.session_marks import (
    MarkConflict, MarkNotFound, MarkServiceError, MarkUnavailable,
)

router = APIRouter()


def _http_from_mark_error(e: Exception) -> HTTPException:
    """MarkConflict→409, MarkNotFound→404, MarkUnavailable→503, other→400."""
    if isinstance(e, MarkConflict):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, MarkNotFound):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, MarkUnavailable):
        return HTTPException(status_code=503, detail=str(e))
    if isinstance(e, MarkServiceError):
        return HTTPException(status_code=400, detail=str(e))
    raise e


@router.post("/sessions/{session_id}/marks")
async def post_session_marks(
    session_id: str, payload: SubmitMarksRequest, request: Request,
):
    svc = require(getattr(request.app.state, "session_marks", None), "session marks")
    try:
        return await svc.submit_marks(
            session_id,
            payload.last_index,
            payload.description,
            [m.model_dump() for m in payload.marks],
        )
    except MarkServiceError as e:
        raise _http_from_mark_error(e)


@router.get("/sessions/{session_id}/marks")
async def get_session_marks(session_id: str, request: Request):
    svc = require(getattr(request.app.state, "session_marks", None), "session marks")
    try:
        return await svc.list_marks(session_id)
    except MarkServiceError as e:
        raise _http_from_mark_error(e)
