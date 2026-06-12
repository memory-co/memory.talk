"""v1 database migration — init (fresh) + up (0.8.x → v1)."""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v1 import init_database, up_database


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


# ─── tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_creates_all_v1_tables_and_indexes(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    await init_database.run(conn)
    tables = await _tables(conn)
    assert tables == {
        "sessions", "cards", "card_stats", "card_source_cards",
        "reviews", "recall_event", "search_log",
    }
    # Spot-check the v1-only columns landed on the right tables.
    sessions_cols = await _cols(conn, "sessions")
    assert "tags" in sessions_cols  # 0.8.x addition
    assert "location" in sessions_cols
    assert "indexed_round_count" in sessions_cols
    cards_cols = await _cols(conn, "cards")
    assert "tags" in cards_cols
    stats_cols = await _cols(conn, "card_stats")
    assert "recall_count" not in stats_cols  # dropped in 0.9
    await conn.close()


@pytest.mark.asyncio
async def test_init_is_idempotent(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    await init_database.run(conn)
    await init_database.run(conn)  # second time mustn't error
    assert "sessions" in await _tables(conn)
    await conn.close()


@pytest.mark.asyncio
async def test_up_brings_081_database_to_v1(tmp_path):
    """Seed a connection with the 0.8.1 table shape, run up, assert
    the schema matches v1 and that the data we cared about (legacy
    rounds_index → sessions.last_round_id) was preserved."""
    conn = await aiosqlite.connect(":memory:")
    # 0.8.1 sessions: no location/tags/last_*/indexed_*.
    await conn.execute(
        "CREATE TABLE sessions ("
        "  session_id TEXT PRIMARY KEY, source TEXT NOT NULL,"
        "  cwd TEXT, created_at TEXT NOT NULL, synced_at TEXT NOT NULL,"
        "  metadata TEXT NOT NULL DEFAULT '{}',"
        "  round_count INTEGER NOT NULL DEFAULT 0)"
    )
    # 0.8.1 cards: no tags column.
    await conn.execute(
        "CREATE TABLE cards (card_id TEXT PRIMARY KEY,"
        " insight TEXT NOT NULL, rounds TEXT NOT NULL DEFAULT '[]',"
        " created_at TEXT NOT NULL)"
    )
    # 0.8.1 card_stats: has the legacy recall_count.
    await conn.execute(
        "CREATE TABLE card_stats ("
        "  card_id TEXT PRIMARY KEY, review_up INT DEFAULT 0,"
        "  review_down INT DEFAULT 0, review_neutral INT DEFAULT 0,"
        "  review_count INT DEFAULT 0, read_count INT DEFAULT 0,"
        "  recall_count INT DEFAULT 0,"
        "  updated_at TEXT NOT NULL)"
    )
    # Legacy 0.8.x tables that v1 drops.
    await conn.execute(
        "CREATE TABLE recall_log (id TEXT PRIMARY KEY,"
        " session_id TEXT, ts TEXT)"
    )
    await conn.execute(
        "CREATE TABLE rounds_index ("
        "  session_id TEXT, idx INT, round_id TEXT)"
    )
    await conn.execute(
        "INSERT INTO sessions VALUES('s1','claude-code','/x',"
        "'2026-01-01','2026-01-01','{}',2)"
    )
    await conn.execute(
        "INSERT INTO rounds_index VALUES('s1', 1, 'r1')"
    )
    await conn.execute(
        "INSERT INTO rounds_index VALUES('s1', 2, 'r2')"
    )
    await conn.execute(
        "INSERT INTO cards VALUES('c1','hello','[]','2026-01-01')"
    )
    await conn.commit()

    await up_database.run(conn)

    sessions_cols = await _cols(conn, "sessions")
    # Added by 0.8.x → v1 ALTERs:
    for col in (
        "location", "location_label", "tags", "last_round_id",
        "indexed_round_count", "last_index_error",
        "last_index_attempted_at",
    ):
        assert col in sessions_cols, f"sessions missing {col}"

    cards_cols = await _cols(conn, "cards")
    assert "tags" in cards_cols

    stats_cols = await _cols(conn, "card_stats")
    assert "recall_count" not in stats_cols

    tables = await _tables(conn)
    assert "recall_log" not in tables  # dropped
    assert "rounds_index" not in tables  # dropped
    assert "recall_event" in tables  # newly created

    # last_round_id was populated from rounds_index's max-idx row
    # before the table was dropped.
    async with conn.execute(
        "SELECT last_round_id FROM sessions WHERE session_id='s1'"
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == "r2"

    await conn.close()


@pytest.mark.asyncio
async def test_up_is_idempotent(tmp_path):
    """Re-running up on an already-v1 schema should be a no-op."""
    conn = await aiosqlite.connect(":memory:")
    await init_database.run(conn)
    await up_database.run(conn)  # should be a no-op
    assert "sessions" in await _tables(conn)
    cols = await _cols(conn, "sessions")
    # And no duplicate columns or anything.
    assert len([c for c in cols if c == "tags"]) == 1
    await conn.close()


@pytest.mark.asyncio
async def test_up_handles_completely_empty_db(tmp_path):
    """A database with no tables (e.g. fresh install reaching up via
    upgrade_from_zero on a stale state.json) still ends up at v1."""
    conn = await aiosqlite.connect(":memory:")
    await up_database.run(conn)
    assert "sessions" in await _tables(conn)
    await conn.close()
