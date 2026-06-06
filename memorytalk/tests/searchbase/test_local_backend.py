"""Contract behavior for the local searchbase backend.

These exercise the generic SearchBackend surface (upsert / search /
delete / delete_where) — no card/round/session vocabulary, just
collections of Docs.
"""
from __future__ import annotations

import pytest

from memorytalk.config import Config
from memorytalk.searchbase import Doc, Query, make_search_backend


@pytest.fixture
async def backend(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    b = make_search_backend(config)
    await b.start()
    try:
        yield b
    finally:
        await b.stop()


async def test_upsert_then_search_returns_doc(backend):
    await backend.upsert("cards", [Doc(id="c1", text="hello world", fields={})])

    hits = await backend.search("cards", Query(text="hello", top_k=5))

    assert any(h.id == "c1" for h in hits)
