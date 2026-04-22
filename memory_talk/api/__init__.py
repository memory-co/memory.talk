"""FastAPI app root. Mounts versioned routers."""
from __future__ import annotations
import os
import sqlite3
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from memory_talk.config import Config
from memory_talk.embedding import EmbedderValidationError, validate_embedder
from memory_talk.storage.init_db import init_db
from memory_talk.v2.storage.schema import init_v2_schema


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.ensure_dirs()
    init_db(config.db_path)

    with sqlite3.connect(config.db_path) as _conn:
        init_v2_schema(_conn)

    try:
        validate_embedder(config)
    except EmbedderValidationError as e:
        print(f"[memory-talk] embedding startup check failed: {e}", file=sys.stderr)
        raise SystemExit(2) from e

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="memory.talk", lifespan=lifespan)
    app.state.config = config

    from memory_talk.api.v1 import router as v1_router
    app.include_router(v1_router, prefix="/v1")
    return app


_data_root = os.environ.get("MEMORY_TALK_DATA_ROOT")
app = create_app(Config(_data_root) if _data_root else Config())
