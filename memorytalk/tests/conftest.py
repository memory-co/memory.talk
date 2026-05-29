"""Shared fixtures.

- ``app_factory``: returns a coroutine factory that builds an in-process
  v3 app rooted at a fresh tmpdir + dummy embedder. Used by integration
  tests that want a live FastAPI / lifespan stack.
- ``async_client``: convenience httpx.AsyncClient bound to that app.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

# Make sure `import memorytalk` works when running tests from the repo root.
# (Editable install isn't guaranteed; this is the test-suite safety net.)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """A fresh, isolated data root with a dummy-embedder settings.json.

    ``index.lance_flush_rows=1`` and ``lance_flush_interval_seconds=0``
    make the IndexWriteBuffer behave like the pre-buffer code path:
    every ``add_rounds`` triggers an immediate flush, the background
    flusher task is disabled. Tests can then assert search visibility
    right after ``ingest_session`` without an explicit flush call.
    """
    settings = {
        "embedding": {"provider": "dummy", "dim": 384},
        "sync": {"debounce_ms": 50},
        "index": {
            "lance_flush_rows": 1,
            "lance_flush_interval_seconds": 0,
        },
    }
    (tmp_path / "settings.json").write_text(json.dumps(settings))
    return tmp_path


@pytest_asyncio.fixture
async def app(data_root, monkeypatch):
    """An app instance booted with its lifespan and bound to ``data_root``."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(data_root))
    from memorytalk.api import create_app
    from memorytalk.config import Config
    a = create_app(Config())
    async with a.router.lifespan_context(a):
        yield a


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac
