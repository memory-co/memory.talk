"""v1_upgrade_from_081 — up_database + up_searchbase against the 0.8.1
shape, plus idempotency / empty-DB / fresh-backend edge cases.

See ``README.md`` for what's in scope.
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite
import pyarrow as pa
import pytest

from memorytalk.migrations.v1 import init_database, up_database, up_searchbase
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


async def _seed_081_lancedb(data_dir: Path, dim: int) -> None:
    import lancedb

    data_dir.mkdir(parents=True, exist_ok=True)
    db = await lancedb.connect_async(str(data_dir))
    cards_schema = pa.schema([
        pa.field("card_id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])
    rounds_schema = pa.schema([
        pa.field("session_id", pa.string()),
        pa.field("idx", pa.int32()),
        pa.field("role", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])
    await db.create_table("cards", schema=cards_schema)
    await db.create_table("rounds", schema=rounds_schema)


# ─── database side ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_up_brings_081_database_to_v1():
    """Seed a connection with the 0.8.1 table shape, run up, assert the
    schema matches v1 and the data we cared about (legacy rounds_index
    → sessions.last_round_id) was preserved."""
    conn = await aiosqlite.connect(":memory:")
    await conn.execute(
        "CREATE TABLE sessions ("
        "  session_id TEXT PRIMARY KEY, source TEXT NOT NULL,"
        "  cwd TEXT, created_at TEXT NOT NULL, synced_at TEXT NOT NULL,"
        "  metadata TEXT NOT NULL DEFAULT '{}',"
        "  round_count INTEGER NOT NULL DEFAULT 0)"
    )
    await conn.execute(
        "CREATE TABLE cards (card_id TEXT PRIMARY KEY,"
        " insight TEXT NOT NULL, rounds TEXT NOT NULL DEFAULT '[]',"
        " created_at TEXT NOT NULL)"
    )
    await conn.execute(
        "CREATE TABLE card_stats ("
        "  card_id TEXT PRIMARY KEY, review_up INT DEFAULT 0,"
        "  review_down INT DEFAULT 0, review_neutral INT DEFAULT 0,"
        "  review_count INT DEFAULT 0, read_count INT DEFAULT 0,"
        "  recall_count INT DEFAULT 0,"
        "  updated_at TEXT NOT NULL)"
    )
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
    await conn.execute("INSERT INTO rounds_index VALUES('s1', 1, 'r1')")
    await conn.execute("INSERT INTO rounds_index VALUES('s1', 2, 'r2')")
    await conn.execute(
        "INSERT INTO cards VALUES('c1','hello','[]','2026-01-01')"
    )
    await conn.commit()

    await up_database.run(conn)

    sessions_cols = await _cols(conn, "sessions")
    for col in (
        "location", "location_label", "tags", "last_round_id",
        "indexed_round_count", "last_index_error",
        "last_index_attempted_at",
    ):
        assert col in sessions_cols, f"sessions missing {col}"

    assert "tags" in await _cols(conn, "cards")
    assert "recall_count" not in await _cols(conn, "card_stats")

    tables = await _tables(conn)
    assert "recall_log" not in tables  # dropped
    assert "rounds_index" not in tables  # dropped
    assert "recall_event" in tables  # newly created

    async with conn.execute(
        "SELECT last_round_id FROM sessions WHERE session_id='s1'"
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == "r2"  # the max-idx round was preserved
    await conn.close()


@pytest.mark.asyncio
async def test_up_database_is_idempotent():
    """Re-running up on an already-v1 schema should be a no-op."""
    conn = await aiosqlite.connect(":memory:")
    await init_database.run(conn)
    await up_database.run(conn)
    assert "sessions" in await _tables(conn)
    cols = await _cols(conn, "sessions")
    assert len([c for c in cols if c == "tags"]) == 1
    await conn.close()


@pytest.mark.asyncio
async def test_up_database_handles_completely_empty_db():
    """A database with no tables (e.g. fresh install reaching up via a
    stale upgrade_from_zero state) still ends up at v1."""
    conn = await aiosqlite.connect(":memory:")
    await up_database.run(conn)
    assert "sessions" in await _tables(conn)
    await conn.close()


# ─── searchbase side ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_up_renames_cards_card_id_to_id(tmp_path):
    dim = 4
    data_dir = tmp_path / "vectors"
    await _seed_081_lancedb(data_dir, dim)
    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections=_V1_COLLECTIONS,
    )
    try:
        admin = backend.admin()
        cols_before = set(await admin.list_columns("cards"))
        assert "card_id" in cols_before and "id" not in cols_before
        await up_searchbase.run(admin)
        cols_after = set(await admin.list_columns("cards"))
        assert "id" in cols_after
        assert "card_id" not in cols_after
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_up_adds_rounds_id_base_id_chunk(tmp_path):
    dim = 4
    data_dir = tmp_path / "vectors"
    await _seed_081_lancedb(data_dir, dim)
    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections=_V1_COLLECTIONS,
    )
    try:
        admin = backend.admin()
        cols_before = set(await admin.list_columns("rounds"))
        for needed in ("id", "_base_id", "_chunk"):
            assert needed not in cols_before
        await up_searchbase.run(admin)
        cols_after = set(await admin.list_columns("rounds"))
        for needed in ("id", "_base_id", "_chunk"):
            assert needed in cols_after, f"rounds missing {needed}"
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_up_searchbase_is_idempotent(tmp_path):
    """Running up twice (e.g. a botched first run that crashed after the
    rename but before recording state) doesn't error."""
    dim = 4
    data_dir = tmp_path / "vectors"
    await _seed_081_lancedb(data_dir, dim)
    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections=_V1_COLLECTIONS,
    )
    try:
        admin = backend.admin()
        await up_searchbase.run(admin)
        await up_searchbase.run(admin)
        cols = set(await admin.list_columns("cards"))
        assert "id" in cols and "card_id" not in cols
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_up_searchbase_noop_on_fresh_backend(tmp_path):
    """Fresh install — LocalSearchBackend auto-creates collections with
    the v1 shape. up should see no work to do."""
    dim = 4
    data_dir = tmp_path / "vectors"
    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections=_V1_COLLECTIONS,
    )
    try:
        admin = backend.admin()
        await up_searchbase.run(admin)
        cols = set(await admin.list_columns("cards"))
        assert "id" in cols and "card_id" not in cols
        rcols = set(await admin.list_columns("rounds"))
        for needed in ("id", "_base_id", "_chunk"):
            assert needed in rcols
    finally:
        await backend.close()
