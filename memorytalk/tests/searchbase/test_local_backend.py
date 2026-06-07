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
    b = await make_search_backend(config, name="v1", collections={"cards": {}})
    try:
        yield b
    finally:
        await b.close()


async def test_upsert_then_search_returns_doc(backend):
    await backend.upsert("cards", [Doc(id="c1", text="hello world", fields={})])

    hits = await backend.search("cards", Query(text="hello", top_k=5))

    assert any(h.id == "c1" for h in hits)


async def test_count_reflects_durable_docs(backend):
    await backend.upsert("cards", [
        Doc(id="c1", text="alpha"),
        Doc(id="c2", text="beta"),
    ])

    assert await backend.count("cards") == 2


async def test_health_exposes_emfile_counters(backend):
    # The sync status panel reads these through health().detail; the
    # backend must surface the index's recovery counters, not drop them.
    health = await backend.health()

    assert "emfile_recoveries" in health.detail


async def test_declared_schema_keeps_field_numeric_despite_null_first_row(data_root):
    # The schema is declared up front, not inferred from the first row.
    # A null score in the first doc must NOT poison the column to string
    # (which would break numeric filtering) — it stays int because the
    # collection declared it int.
    config = Config(data_root)
    config.ensure_dirs()
    b = await make_search_backend(
        config, name="v1", collections={"items": {"score": "int"}},
    )
    try:
        await b.upsert("items", [
            Doc(id="a", text="x", fields={"score": None}),
            Doc(id="b", text="y", fields={"score": 5}),
        ])
        assert await b.count("items", {"score": 5}) == 1
    finally:
        await b.close()


async def test_emfile_recovery_repopulates_collections(backend):
    # Recovery compacts every known collection. If the known-set is
    # stale/empty (e.g. a read-only boot whose initial list_tables
    # failed), recovery must re-list tables so it actually compacts
    # something instead of looping over nothing.
    await backend.upsert("cards", [Doc(id="c1", text="x")])
    index = backend._index
    index._collections.clear()

    await index._recover_from_emfile()

    assert "cards" in index._collections
