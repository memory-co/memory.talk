"""v1_baseline — init_database + init_searchbase on a fresh slate.

See ``README.md`` for what's in scope.
"""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v1 import init_database, init_searchbase
from memorytalk.searchbase import LocalSearchBackend


# ─── helpers ───────────────────────────────────────────────────────


async def _cols(conn, table: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        return {row[1] for row in await cur.fetchall()}


async def _tables(conn) -> set[str]:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


class _DummyEmbedder:
    def __init__(self, dim: int):
        self.dim = dim

    async def embed(self, texts):
        return [[0.0] * self.dim for _ in texts]

    async def embed_one(self, text):
        return [0.0] * self.dim


_V1_COLLECTIONS = {
    "cards": {"fields": {}},
    "rounds": {
        "fields": {"session_id": "str", "idx": "int", "role": "str"},
        "auto_split": True,
    },
}


# ─── database ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_database_creates_all_v1_tables():
    conn = await aiosqlite.connect(":memory:")
    await init_database.run(conn)
    assert await _tables(conn) == {
        "sessions", "cards", "card_stats", "card_source_cards",
        "reviews", "recall_event", "search_log", "explores",
    }
    sessions_cols = await _cols(conn, "sessions")
    assert "tags" in sessions_cols
    assert "location" in sessions_cols
    assert "indexed_round_count" in sessions_cols
    assert "last_round_update_time" in sessions_cols
    cards_cols = await _cols(conn, "cards")
    assert "tags" in cards_cols
    assert "explore_id" in cards_cols
    assert "explore_id" in await _cols(conn, "reviews")
    stats_cols = await _cols(conn, "card_stats")
    assert "recall_count" not in stats_cols  # dropped in 0.9
    await conn.close()


@pytest.mark.asyncio
async def test_init_database_is_idempotent():
    conn = await aiosqlite.connect(":memory:")
    await init_database.run(conn)
    await init_database.run(conn)  # second time mustn't error
    assert "sessions" in await _tables(conn)
    await conn.close()


# ─── searchbase ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_searchbase_leaves_collections_at_v1_shape(tmp_path):
    """The backend's constructor already creates declared collections,
    so init is a no-op — but the v1 shape must be in place either way."""
    backend = await LocalSearchBackend.create(
        data_dir=tmp_path / "vectors", dim=4,
        embedder=_DummyEmbedder(4),
        collections=_V1_COLLECTIONS,
    )
    try:
        admin = backend.admin()
        await init_searchbase.run(admin)
        cards_cols = set(await admin.list_columns("cards"))
        assert "id" in cards_cols and "card_id" not in cards_cols
        rounds_cols = set(await admin.list_columns("rounds"))
        for needed in ("id", "_base_id", "_chunk"):
            assert needed in rounds_cols
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_init_searchbase_is_idempotent(tmp_path):
    backend = await LocalSearchBackend.create(
        data_dir=tmp_path / "vectors", dim=4,
        embedder=_DummyEmbedder(4),
        collections=_V1_COLLECTIONS,
    )
    try:
        admin = backend.admin()
        await init_searchbase.run(admin)
        await init_searchbase.run(admin)
        collections = set(await admin.list_collections())
        assert "cards" in collections and "rounds" in collections
    finally:
        await backend.close()
