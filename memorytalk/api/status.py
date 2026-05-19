"""GET /v3/status — server info + stats."""
from __future__ import annotations
from fastapi import APIRouter, Request

from memorytalk.schemas import StatusResponse

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    config = request.app.state.config
    db = request.app.state.db
    sync_svc = request.app.state.sync
    sync_enabled = bool(sync_svc and getattr(sync_svc, "running", False))
    return StatusResponse(
        data_root=str(config.data_root),
        settings_path=str(config.settings_path),
        status="running",
        sessions_total=await db.sessions.count(),
        cards_total=await db.cards.count(),
        reviews_total=await db.reviews.count(),
        searches_total=await db.search_log.count(),
        recalls_total=await db.recall.count(),
        embedding_provider=config.settings.embedding.provider,
        embedding_model=config.settings.embedding.model,
        embedding_dim=config.settings.embedding.dim,
        vector_provider=config.settings.vector.provider,
        relation_provider=config.settings.relation.provider,
        sync_enabled=sync_enabled,
    )
