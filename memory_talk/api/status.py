from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/status")
def status(request: Request):
    from memory_talk.storage.sqlite import SQLiteStore
    config = request.app.state.config
    db = SQLiteStore(config.db_path)
    return {
        "sessions_total": db.count_sessions(),
        "cards_total": db.count_cards(),
        "links_total": db.count_links(),
        "vector_provider": config.settings.vector.provider,
        "relation_provider": config.settings.relation.provider,
        "embedding_provider": config.settings.embedding.provider,
    }

@router.post("/rebuild")
def rebuild(request: Request):
    from memory_talk.service.rebuild import rebuild_async
    rebuild_async(request.app.state.config)
    return {"status": "rebuilding"}
