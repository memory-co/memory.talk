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
    # id VALUE rewritten card_x → insight_x (column name stays card_id).
    async with conn.execute("SELECT insight FROM insights WHERE card_id='insight_x'") as c:
        assert (await c.fetchone())[0] == "hi"
    async with conn.execute("SELECT COUNT(*) FROM insights WHERE card_id LIKE 'card_%'") as c:
        assert (await c.fetchone())[0] == 0
    await conn.close()


@pytest.mark.asyncio
async def test_v3_up_rewrites_source_card_and_recall_ids(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)
    await v2_up.run(conn, data_root=None)
    await conn.execute(
        "INSERT INTO cards (card_id, insight, rounds, tags, created_at) "
        "VALUES ('card_a','a','[]','{}','t')")
    await conn.execute(
        "INSERT INTO cards (card_id, insight, rounds, tags, created_at) "
        "VALUES ('card_b','b','[]','{}','t')")
    await conn.execute(
        "INSERT INTO card_source_cards (card_id, seq, source_card_id, relation) "
        "VALUES ('card_b', 0, 'card_a', 'derives_from')")
    await conn.execute(
        "INSERT INTO recall_event "
        "(event_id, session_id, prompt, ts, returned_ids, skipped_ids) "
        "VALUES ('rc_1','sess_x','p','t','[\"card_a\",\"card_b\"]','[\"card_a\"]')")
    await conn.commit()
    await v3_up.run(conn, data_root=tmp_path)
    async with conn.execute(
        "SELECT card_id, source_card_id FROM insight_source_cards") as c:
        row = await c.fetchone()
    assert row[0] == "insight_b" and row[1] == "insight_a"
    async with conn.execute(
        "SELECT returned_ids, skipped_ids FROM recall_event WHERE event_id='rc_1'") as c:
        ret, skip = await c.fetchone()
    assert ret == '["insight_a","insight_b"]'
    assert skip == '["insight_a"]'
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
    # dir moved cards/ → insights/ AND leaf renamed card_x → insight_x;
    # bucket dir (01) unchanged.
    assert (tmp_path / "insights" / "01" / "insight_x").exists()
    assert not (tmp_path / "insights" / "01" / "card_x").exists()
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
