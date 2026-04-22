"""GET /v2/status — stats and running info."""
from __future__ import annotations
from fastapi import APIRouter, Request

from memory_talk_v2.models import StatusOut

router = APIRouter()


@router.get("/status", response_model=StatusOut)
async def get_status(request: Request) -> StatusOut:
    config = request.app.state.config
    db = request.app.state.db
    return StatusOut(
        data_root=str(config.data_root),
        settings_path=str(config.settings_path),
        status="running",
        sessions_total=db.count_sessions(),
        cards_total=db.count_cards(),
        links_total=db.count_links(),
        searches_total=db.count_search_log(),
        vector_provider=config.settings.vector.provider,
        relation_provider=config.settings.relation.provider,
        embedding_provider=config.settings.embedding.provider,
    )
