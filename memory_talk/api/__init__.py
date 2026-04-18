"""FastAPI application."""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from memory_talk.config import Config
from memory_talk.storage.init_db import init_db

def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.ensure_dirs()
    init_db(config.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="memory.talk", lifespan=lifespan)
    app.state.config = config

    from memory_talk.api import sessions, cards, links, recall, status
    app.include_router(sessions.router)
    app.include_router(cards.router)
    app.include_router(links.router)
    app.include_router(recall.router)
    app.include_router(status.router)
    return app

# Module-level app for uvicorn
_data_root = os.environ.get("MEMORY_TALK_DATA_ROOT")
app = create_app(Config(_data_root) if _data_root else Config())
