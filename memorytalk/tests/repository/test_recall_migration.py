"""Schema migration: 0.8.x → 0.9.0.

Verifies that ``init_schema`` against a legacy 0.8.x DB:
- drops ``recall_log`` table + its index
- drops ``card_stats.recall_count`` column
- creates ``recall_event`` table + its index
"""
from __future__ import annotations
import aiosqlite
import pytest

from memorytalk.repository.schema import init_schema

pytestmark = pytest.mark.asyncio


async def _legacy_schema(conn: aiosqlite.Connection) -> None:
    """Seed a fake 0.8.x DB with just the relevant tables — enough to
    drive the migration code path."""
    await conn.execute(
        "CREATE TABLE card_stats ("
        "  card_id TEXT PRIMARY KEY, "
        "  review_up INTEGER NOT NULL DEFAULT 0, "
        "  review_down INTEGER NOT NULL DEFAULT 0, "
        "  review_neutral INTEGER NOT NULL DEFAULT 0, "
        "  review_count INTEGER NOT NULL DEFAULT 0, "
        "  read_count INTEGER NOT NULL DEFAULT 0, "
        "  recall_count INTEGER NOT NULL DEFAULT 0, "
        "  updated_at TEXT NOT NULL"
        ")"
    )
    await conn.execute(
        "CREATE TABLE recall_log ("
        "  session_id TEXT NOT NULL, "
        "  card_id TEXT NOT NULL, "
        "  recalled_at TEXT NOT NULL, "
        "  PRIMARY KEY (session_id, card_id)"
        ")"
    )
    await conn.execute(
        "CREATE INDEX idx_recall_log_session ON recall_log(session_id)"
    )
    await conn.execute(
        "INSERT INTO card_stats "
        "(card_id, review_up, review_down, review_neutral, review_count, "
        " read_count, recall_count, updated_at) "
        "VALUES ('card_x', 1, 0, 0, 1, 5, 42, '2026-05-29T00:00:00Z')"
    )
    await conn.execute(
        "INSERT INTO recall_log VALUES ('sess-x', 'card_x', '2026-05-29Z')"
    )
    await conn.commit()


async def test_migration_drops_recall_log_and_recall_count(tmp_path):
    db_path = tmp_path / "memory.db"
    async with aiosqlite.connect(db_path) as conn:
        await _legacy_schema(conn)

    async with aiosqlite.connect(db_path) as conn:
        await init_schema(conn)

        async with conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table','index') AND name LIKE 'recall_log%'"
        ) as cur:
            rows = await cur.fetchall()
        assert rows == []

        # recall_event table exists.
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recall_event'"
        ) as cur:
            assert (await cur.fetchone()) is not None
        # its (session, ts) index exists too.
        async with conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name LIKE 'idx_recall_event%'"
        ) as cur:
            assert (await cur.fetchone()) is not None

        async with conn.execute("PRAGMA table_info(card_stats)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        assert "recall_count" not in cols
        for col in ("review_up", "review_down", "review_neutral",
                    "review_count", "read_count", "updated_at"):
            assert col in cols


async def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "memory.db"
    async with aiosqlite.connect(db_path) as conn:
        await _legacy_schema(conn)
    async with aiosqlite.connect(db_path) as conn:
        await init_schema(conn)
    async with aiosqlite.connect(db_path) as conn:
        await init_schema(conn)  # second pass must be no-op-ish


async def test_migration_works_on_fresh_db(tmp_path):
    db_path = tmp_path / "memory.db"
    async with aiosqlite.connect(db_path) as conn:
        await init_schema(conn)
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recall_event'"
        ) as cur:
            assert (await cur.fetchone()) is not None
        async with conn.execute("PRAGMA table_info(card_stats)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        assert "recall_count" not in cols
