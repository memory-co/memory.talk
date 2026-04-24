"""GET /v2/status — stats and running info."""
from __future__ import annotations
from fastapi import APIRouter, Request

from memory_talk_v2.schemas import StatusResponse

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    config = request.app.state.config
    db = request.app.state.db
    return StatusResponse(
        data_root=str(config.data_root),
        settings_path=str(config.settings_path),
        status="running",
        sessions_total=await db.sessions.count(),
        cards_total=await db.cards.count(),
        links_total=await db.links.count(),
        searches_total=await db.search_log.count(),
        vector_provider=config.settings.vector.provider,
        relation_provider=config.settings.relation.provider,
        embedding_provider=config.settings.embedding.provider,
    )
