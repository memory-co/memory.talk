"""FastAPI app factory for v3.

Async startup via lifespan: open SQLite + LanceDB, probe the embedding
provider, wire services into ``app.state``.

Optional services that depend on optional providers (vector store) are
constructed defensively — if a dep is unavailable the app still starts
and the dependent endpoint returns 503 ``unavailable`` (rather than the
whole server failing to come up).
"""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from memorytalk.config import Config, ConfigValidationError


_log = logging.getLogger("memorytalk.api")
from memorytalk.provider.embedding import (
    EmbedderValidationError, get_embedder, validate_embedder,
)
from memorytalk.provider.lancedb import LanceStore
from memorytalk.provider.storage import LocalStorage
from memorytalk.repository import SQLiteStore
from memorytalk.service import (
    CardService, EventWriter, IngestService, ReadService,
    RecallService, ReviewService,
)
from memorytalk.service.search import SearchService
from memorytalk.service.sync import SyncWatcher


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.ensure_dirs()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage = LocalStorage(config.data_root)
        db = await SQLiteStore.create(config.db_path, storage)

        # LanceDB is optional at boot. If it can't open (missing pyarrow,
        # bad dir perms, ...) we still want read/status to work.
        vectors: LanceStore | None = None
        try:
            vectors = await LanceStore.create(
                config.vectors_dir, dim=config.settings.embedding.dim,
            )
        except Exception:
            _log.exception("lancedb init failed; vector-backed endpoints will 503")

        embedder = get_embedder(config)

        try:
            await validate_embedder(config)
        except EmbedderValidationError as e:
            _log.exception("embedding startup check failed; aborting boot")
            raise SystemExit(2) from e

        events = EventWriter(db)
        app.state.config = config
        app.state.storage = storage
        app.state.db = db
        app.state.vectors = vectors
        app.state.embedder = embedder
        app.state.events = events
        app.state.read = ReadService(db=db, events=events)
        app.state.ingest = IngestService(
            db=db, vectors=vectors, embedder=embedder, events=events,
        )
        app.state.sync = SyncWatcher(config=config, ingest=app.state.ingest)
        app.state.search = SearchService(
            config=config, db=db, vectors=vectors, embedder=embedder,
        )
        app.state.cards = CardService(
            db=db, vectors=vectors, embedder=embedder, events=events,
        )
        app.state.reviews = ReviewService(db=db, events=events)
        app.state.recall = RecallService(
            config=config, db=db, vectors=vectors, embedder=embedder,
        )

        # Spin up the watcher if settings says so. start() returns fast
        # now — backfill runs as a background task; uvicorn's "startup
        # complete" log is no longer gated on the initial ingest.
        if config.settings.sync.enabled:
            try:
                await app.state.sync.start()
            except Exception:
                _log.exception("sync auto-start failed")

        yield

        # Pause (not stop) on shutdown — preserves the user's persisted
        # enable choice so the next server start auto-resumes the watcher.
        try:
            await app.state.sync.pause()
        except Exception:
            pass
        await db.close()

    app = FastAPI(title="memory.talk v3", lifespan=lifespan)
    app.state.config = config

    # Mount the v3 routers. Each module exports a ``router``; missing
    # modules are silently skipped so partial-build environments still
    # come up (useful during incremental implementation).
    from memorytalk.api.status import router as status_router
    app.include_router(status_router, prefix="/v3")
    from memorytalk.api.read import router as read_router
    app.include_router(read_router, prefix="/v3")
    from memorytalk.api.sessions import router as sessions_router
    app.include_router(sessions_router, prefix="/v3")

    # Optional routers — lazy import so missing ones don't break boot.
    for name in ("sync", "search", "cards", "reviews", "recall"):
        try:
            mod = __import__(f"memorytalk.api.{name}", fromlist=["router"])
            app.include_router(mod.router, prefix="/v3")
        except ImportError:
            pass

    return app


# uvicorn entry point. The data_root env var is the same test hook
# `Config.__init__` honors; user-facing CLI hardcodes ~/.memory-talk.
_data_root = os.environ.get("MEMORY_TALK_DATA_ROOT")
app = create_app(Config(_data_root) if _data_root else Config())
