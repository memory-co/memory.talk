"""v3_insight_rename -- rename cards→insights, drop reviews; fresh init. See README.md."""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v1 import init_database as v1_init
from memorytalk.migrations.v2 import up_database as v2_up
from memorytalk.migrations.v3 import up_database as v3_up
from memorytalk.migrations.v3 import init_database as v3_init


async def _tables(conn):
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_v3_up_renames_and_drops(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)
    await v2_up.run(conn, data_root=None)
    await conn.execute(
        "INSERT INTO cards (card_id, insight, rounds, tags, created_at) "
        "VALUES ('card_x','hi','[]','{}','t')")
    await conn.commit()
    await v3_up.run(conn, data_root=tmp_path)
    t = await _tables(conn)
    assert {"insights", "insight_stats", "insight_source_cards"} <= t
    assert "cards" not in t and "reviews" not in t and "card_stats" not in t
    async with conn.execute("SELECT insight FROM insights WHERE card_id='card_x'") as c:
        assert (await c.fetchone())[0] == "hi"
    await conn.close()


@pytest.mark.asyncio
async def test_v3_up_idempotent(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)
    await v2_up.run(conn, data_root=None)
    await v3_up.run(conn, data_root=tmp_path)
    await v3_up.run(conn, data_root=tmp_path)
    assert "insights" in await _tables(conn)
    await conn.close()


@pytest.mark.asyncio
async def test_v3_up_moves_file_dir(tmp_path):
    (tmp_path / "cards" / "01" / "card_x").mkdir(parents=True)
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)
    await v2_up.run(conn, data_root=None)
    await v3_up.run(conn, data_root=tmp_path)
    assert (tmp_path / "insights" / "01" / "card_x").exists()
    assert not (tmp_path / "cards").exists()
    await conn.close()


@pytest.mark.asyncio
async def test_v3_init_fresh_has_insight_tables_no_reviews():
    conn = await aiosqlite.connect(":memory:")
    await v3_init.run(conn, data_root=None)
    t = await _tables(conn)
    assert {"insights", "insight_stats", "insight_source_cards", "sessions",
            "explores", "recall_event", "search_log"} <= t
    assert "reviews" not in t and "cards" not in t
    await conn.close()
