"""/v4 sessions — reverse lookup: which cards did a session inspire."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from memorytalk.util.ids import SESSION_PREFIX, SESSION_PREFIX_LEGACY

router = APIRouter()


@router.get("/sessions/{session_id}/cards")
async def get_session_cards(session_id: str, request: Request):
    if not (session_id.startswith(SESSION_PREFIX) or session_id.startswith(SESSION_PREFIX_LEGACY)):
        raise HTTPException(status_code=400, detail="invalid session_id prefix")
    db = request.app.state.db
    # card_sessions (mark-grounded provenance) is the canonical card↔session
    # edge, but its write-path is the deferred mark phase. position_sessions
    # (a Position's --source) is the provenance feature that exists today, so
    # we union both for the reverse lookup.
    rows = await db.card_sessions.list_cards_for_session(session_id)
    pos_rows = await db.position_sessions.list_positions_for_session(session_id)
    seen = {r["card_id"] for r in rows}
    for pr in pos_rows:
        if pr["card_id"] not in seen:
            rows.append(pr)
            seen.add(pr["card_id"])
    return {"session_id": session_id, "cards": rows}
