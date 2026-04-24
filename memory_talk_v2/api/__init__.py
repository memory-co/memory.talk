"""FastAPI app factory for v2.

create_app() performs fail-fast startup:
  1) Config.validate() — refuse v1 residue
  2) init SQLite schema
  3) validate_embedder() — probe the configured provider
  4) mount routes at /v2
"""
from __future__ import annotations
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from memory_talk_v2.config import Config, ConfigValidationError
from memory_talk_v2.embedding import (
    EmbedderValidationError,
    get_embedder,
    validate_embedder,
)
from memory_talk_v2.service import (
    CardService, EventWriter, LinkService, RebuildService,
    SearchService, ServiceContext, SessionService,
)
from memory_talk_v2.storage.jsonl_writer import DatedJsonlWriter
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    try:
        config.validate()
    except ConfigValidationError as e:
        print(f"[memory-talk] config validation failed: {e}", file=sys.stderr)
        raise SystemExit(2) from e

    config.ensure_dirs()

    db = SQLiteStore(config.db_path)
    vectors = LanceStore(config.vectors_dir, dim=config.settings.embedding.dim)
    embedder = get_embedder(config)
    search_jsonl = DatedJsonlWriter(config.search_log_dir)
    events = EventWriter(config, db)

    try:
        validate_embedder(config)
    except EmbedderValidationError as e:
        print(f"[memory-talk] embedding startup check failed: {e}", file=sys.stderr)
        raise SystemExit(2) from e

    ctx = ServiceContext(
        config=config, db=db, vectors=vectors, embedder=embedder,
        search_jsonl=search_jsonl, events=events,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        db.close()

    app = FastAPI(title="memory.talk v2", lifespan=lifespan)
    app.state.config = config
    app.state.db = db
    app.state.vectors = vectors
    app.state.embedder = embedder
    app.state.search_jsonl = search_jsonl
    # Service instances — one per noun (plus cross-cutting search / rebuild).
    app.state.sessions = SessionService(ctx)
    app.state.cards = CardService(ctx)
    app.state.links = LinkService(ctx)
    app.state.search = SearchService(ctx)
    app.state.rebuild = RebuildService(ctx)

    from memory_talk_v2.api.status import router as status_router
    app.include_router(status_router, prefix="/v2")

    for name in ("sessions", "cards", "links", "tags", "search", "view", "log", "rebuild"):
        try:
            mod = __import__(f"memory_talk_v2.api.{name}", fromlist=["router"])
            app.include_router(mod.router, prefix="/v2")
        except ImportError:
            pass

    return app


_data_root = os.environ.get("MEMORY_TALK_DATA_ROOT")
app = create_app(Config(_data_root) if _data_root else Config())
