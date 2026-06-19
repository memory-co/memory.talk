"""v4_card_tables — migration v4 creates the 5 v4 tables atop v3. See README.md."""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v3 import init_database as v3_init
from memorytalk.migrations.v4 import up_database as v4_up
from memorytalk.migrations.v4 import init_database as v4_init


async def _tables(conn):
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_v4_up_creates_v4_tables_on_v3():
    conn = await aiosqlite.connect(":memory:")
    await v3_init.run(conn, data_root=None)
    await v4_up.run(conn, data_root=None)
    t = await _tables(conn)
    assert {"cards", "positions", "reviews", "card_links", "card_sessions"} <= t
    assert {"insights", "insight_stats"} <= t   # v3 insight tables coexist
    await conn.close()


@pytest.mark.asyncio
async def test_v4_up_idempotent():
    conn = await aiosqlite.connect(":memory:")
    await v3_init.run(conn, data_root=None)
    await v4_up.run(conn, data_root=None)
    await v4_up.run(conn, data_root=None)   # second run must not error
    assert {"cards", "positions"} <= await _tables(conn)
    await conn.close()


@pytest.mark.asyncio
async def test_v4_init_fresh_has_both():
    conn = await aiosqlite.connect(":memory:")
    await v4_init.run(conn, data_root=None)
    t = await _tables(conn)
    assert {"cards", "positions", "card_links", "card_sessions", "insights"} <= t
    await conn.close()
