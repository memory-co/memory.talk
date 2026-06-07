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
    EmbedderValidationError, validate_embedder,
)
from memorytalk.provider.storage import LocalStorage
from memorytalk.repository import SQLiteStore
from memorytalk.repository.sync_checkpoint import SyncCheckpointStore
from memorytalk.searchbase import make_search_backend
from memorytalk.service import (
    CardService, EventWriter, IngestService, ReadService,
    RecallService, ReviewService,
)
from memorytalk.service.backfill import IndexBackfill
from memorytalk.service.search import SearchService
from memorytalk.service.searchbase_schema import (
    INSTANCE_NAME, MAX_TEXT_LENGTH, SCHEMAS,
)
from memorytalk.service.sync import SyncWatcher


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.ensure_dirs()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage = LocalStorage(config.data_root)
        db = await SQLiteStore.create(config.db_path, storage)
        sync_checkpoints = await SyncCheckpointStore.create(config.sync_db_path)

        try:
            await validate_embedder(config)
        except EmbedderValidationError as e:
            _log.exception("embedding startup check failed; aborting boot")
            raise SystemExit(2) from e

        # searchbase is optional at boot. If it can't open (missing
        # pyarrow, bad dir perms, ...) we still want read/status to work;
        # vector-backed endpoints then return 503 ``unavailable``.
        searchbase = None
        try:
            searchbase = await make_search_backend(
                config, name=INSTANCE_NAME, collections=SCHEMAS,
                max_text_length=MAX_TEXT_LENGTH,
            )
        except Exception:
            _log.exception("searchbase init failed; vector-backed endpoints will 503")

        events = EventWriter(db)
        app.state.config = config
        app.state.storage = storage
        app.state.db = db
        app.state.searchbase = searchbase
        app.state.events = events
        app.state.read = ReadService(db=db, events=events)
        app.state.ingest = IngestService(
            db=db, search=searchbase, events=events,
        )
        app.state.sync_checkpoints = sync_checkpoints
        app.state.sync = SyncWatcher(
            config=config, ingest=app.state.ingest,
            checkpoints=sync_checkpoints,
        )
        app.state.search = SearchService(
            config=config, db=db, search=searchbase,
        )
        app.state.cards = CardService(
            db=db, search=searchbase, events=events,
        )
        app.state.reviews = ReviewService(db=db, events=events)
        app.state.recall = RecallService(
            config=config, db=db, search=searchbase,
        )

        # Spin up the watcher if settings says so. start() returns fast
        # now — backfill runs as a background task; uvicorn's "startup
        # complete" log is no longer gated on the initial ingest.
        if config.settings.sync.enabled:
            try:
                await app.state.sync.start()
            except Exception:
                _log.exception("sync auto-start failed")

        # Vector-index backfill loop — picks up sessions whose
        # ``indexed_round_count < round_count`` (i.e. previous ingest
        # batches failed silently because of e.g. DashScope's 10-cap)
        # and re-embeds them in the background. Disabled gracefully
        # when no embedder / lance is available; loop is cancelled on
        # lifespan shutdown.
        app.state.backfill = IndexBackfill(
            db=db, search=searchbase,
        )
        app.state.backfill.start()
        # Startup compaction is now owned by searchbase (compact_all runs
        # in the background from make_search_backend), so backfill no
        # longer triggers it here.

        yield

        # Pause (not stop) on shutdown — preserves the user's persisted
        # enable choice so the next server start auto-resumes the watcher.
        try:
            await app.state.sync.pause()
        except Exception:
            pass
        try:
            await app.state.backfill.stop()
        except Exception:
            pass
        # Shut down the searchbase instance (stops its maintenance task).
        if app.state.searchbase is not None:
            try:
                await app.state.searchbase.close()
            except Exception:
                pass
        await db.close()
        await sync_checkpoints.close()

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
# `Config.__init__` honors; user-facing CLI hardcodes ~/.memory.talk.
_data_root = os.environ.get("MEMORY_TALK_DATA_ROOT")
app = create_app(Config(_data_root) if _data_root else Config())
