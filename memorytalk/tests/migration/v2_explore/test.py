"""v2_explore — the explore schema delta (v1 → v2). See README.md."""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v1 import init_database as v1_init
from memorytalk.migrations.v2 import init_database as v2_init
from memorytalk.migrations.v2 import up_database as v2_up


async def _cols(conn, table: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        return {row[1] for row in await cur.fetchall()}


async def _tables(conn) -> set[str]:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_v2_init_has_explores_table_and_columns():
    conn = await aiosqlite.connect(":memory:")
    await v2_init.run(conn)
    assert "explores" in await _tables(conn)
    assert "last_round_update_time" in await _cols(conn, "sessions")
    assert "explore_id" in await _cols(conn, "cards")
    assert "explore_id" in await _cols(conn, "reviews")
    await conn.close()


@pytest.mark.asyncio
async def test_v2_up_upgrades_a_v1_database():
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn)                       # a v1 DB — no explore yet
    assert "explores" not in await _tables(conn)

    await v2_up.run(conn)                          # v1 → v2

    assert "explores" in await _tables(conn)
    assert "last_round_update_time" in await _cols(conn, "sessions")
    assert "explore_id" in await _cols(conn, "cards")
    assert "explore_id" in await _cols(conn, "reviews")
    await conn.close()


@pytest.mark.asyncio
async def test_v2_up_is_idempotent():
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn)
    await v2_up.run(conn)
    await v2_up.run(conn)        # second run must not error
    assert "explores" in await _tables(conn)
    await conn.close()
