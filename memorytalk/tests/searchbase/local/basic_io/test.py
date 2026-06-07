"""basic_io — 核心读写 round-trip 场景. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.config import Config
from memorytalk.searchbase import Doc, Query, SearchError
from memorytalk.tests.searchbase.local.conftest import make_backend


# ────────── upsert / search / count happy path ──────────

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


# ────────── text length cap ──────────

async def test_upsert_rejects_text_over_max_length(data_root):
    """Over-length writes are rejected (no silent truncation). The
    business caps text upstream."""
    config = Config(data_root)
    config.ensure_dirs()
    b = await make_backend(
        config, collections={"cards": {"fields": {}}}, max_text_length=10,
    )
    try:
        with pytest.raises(SearchError):
            await b.upsert("cards", [Doc(id="c1", text="x" * 11)])
    finally:
        await b.close()


# ────────── declared schema vs first-row inference ──────────

async def test_declared_schema_keeps_field_numeric_despite_null_first_row(data_root):
    """The schema is declared up front, not inferred from the first row.
    A null score in the first doc must NOT poison the column to string
    (which would break numeric filtering) — it stays int because the
    collection declared it int."""
    config = Config(data_root)
    config.ensure_dirs()
    b = await make_backend(
        config, collections={"items": {"fields": {"score": "int"}}},
    )
    try:
        await b.upsert("items", [
            Doc(id="a", text="x", fields={"score": None}),
            Doc(id="b", text="y", fields={"score": 5}),
        ])
        assert await b.count("items", {"score": 5}) == 1
    finally:
        await b.close()
