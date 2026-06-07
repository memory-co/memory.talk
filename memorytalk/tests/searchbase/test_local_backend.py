"""Contract behavior for the local searchbase backend.

These exercise the generic SearchBackend surface (upsert / search /
delete / delete_where) — no card/round/session vocabulary, just
collections of Docs.
"""
from __future__ import annotations

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import get_embedder
from memorytalk.searchbase import Doc, LocalSearchBackend, Query, SearchError


async def _make_backend(config, *, collections, max_text_length=100_000):
    """Build a backend from plain values (searchbase takes no Config)."""
    return await LocalSearchBackend.create(
        name="v1", data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim, embedder=get_embedder(config),
        collections=collections, max_text_length=max_text_length,
    )


@pytest.fixture
async def backend(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    b = await _make_backend(config, collections={"cards": {}})
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


async def test_upsert_rejects_text_over_max_length(data_root):
    # searchbase declares a max text length; over-length writes are
    # rejected (no silent truncation). The business caps text upstream.
    config = Config(data_root)
    config.ensure_dirs()
    b = await _make_backend(config, collections={"cards": {}}, max_text_length=10)
    try:
        with pytest.raises(SearchError):
            await b.upsert("cards", [Doc(id="c1", text="x" * 11)])
    finally:
        await b.close()


@pytest.mark.skip(reason="auto_split not implemented yet — RED for the next step")
async def test_auto_split_collection_hides_chunking(data_root):
    # A collection declared with auto_split splits over-length text into
    # multiple internal rows, but the chunking is invisible: count is by
    # logical doc, search collapses to one hit, delete removes all chunks.
    config = Config(data_root)
    config.ensure_dirs()
    b = await _make_backend(
        config,
        collections={"notes": {"fields": {}, "auto_split": True}},
        max_text_length=10,
    )
    try:
        # 25 chars at max 10 → 3 internal chunks, but ONE logical doc.
        await b.upsert("notes", [Doc(id="n1", text="alpha beta gamma delta eps")])
        assert await b.count("notes") == 1

        hits = await b.search("notes", Query(text="gamma", top_k=5))
        ids = [h.id for h in hits]
        assert ids.count("n1") == 1  # collapsed, not three chunk hits
        assert "n1#0" not in ids     # internal chunk ids never leak out

        await b.delete("notes", ["n1"])
        assert await b.count("notes") == 0  # all chunks gone
    finally:
        await b.close()


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
    b = await _make_backend(config, collections={"items": {"score": "int"}})
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
