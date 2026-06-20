"""GET /v3/status — server info + stats."""
from __future__ import annotations
from fastapi import APIRouter, Request

from memorytalk.schemas import StatusResponse

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    config = request.app.state.config
    db = request.app.state.db
    sync_enabled = bool(config.settings.sync.enabled)
    # Flip to ``reembedding`` (with the processed-so-far count) while a
    # searchbase reembed run holds the in-progress guard; otherwise the
    # normal ``running`` with no reembed field.
    reembed = getattr(request.app.state, "reembed", None)
    reembedding = reembed is not None and reembed.running
    return StatusResponse(
        data_root=str(config.data_root),
        settings_path=str(config.settings_path),
        status="reembedding" if reembedding else "running",
        reembed_processed=reembed.processed if reembedding else None,
        sessions_total=await db.sessions.count(),
        # Real v4 cards (was previously mislabeled as the insight count).
        cards_total=await db.cards.count(),
        insights_total=await db.insights.count(),
        # reviews retired (v3→insight); field kept as a vestigial 0 to
        # avoid churning the status contract (mirrors the kept-but-unwritten
        # insight_stats review_* columns).
        reviews_total=0,
        searches_total=await db.search_log.count(),
        recalls_total=await db.recall.count(),
        embedding_provider=config.settings.embedding.provider,
        embedding_model=config.settings.embedding.model,
        embedding_dim=config.settings.embedding.dim,
        vector_provider=config.settings.vector.provider,
        relation_provider=config.settings.relation.provider,
        sync_enabled=sync_enabled,
    )
