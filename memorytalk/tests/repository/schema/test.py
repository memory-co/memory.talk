"""schema -- v4 DDL creates the 5 tables with the right columns. See README.md."""
from __future__ import annotations


async def _columns(conn, table):
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        return {row["name"] for row in await cur.fetchall()}


async def test_five_tables_exist(v4db):
    async with v4db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cur:
        names = {r["name"] for r in await cur.fetchall()}
    assert {"cards", "positions", "reviews", "card_links", "card_sessions"} <= names


async def test_cards_has_redundant_counters(v4db):
    cols = await _columns(v4db.conn, "cards")
    assert {"card_id", "issue", "created_at", "position_count", "link_count"} == cols


async def test_positions_has_counts_and_governance(v4db):
    cols = await _columns(v4db.conn, "positions")
    assert {"up_count", "down_count", "neutral_count", "review_count",
            "scope", "forked_from_position_id"} <= cols
    assert "credence" not in cols  # credence is computed, never stored


async def test_card_links_has_target_type(v4db):
    cols = await _columns(v4db.conn, "card_links")
    assert {"card_id", "type", "target_id", "target_type"} <= cols


async def test_reviews_columns(v4db):
    cols = await _columns(v4db.conn, "reviews")
    assert {"review_id", "position_id", "card_id", "session_id",
            "indexes", "argument", "comment", "created_at"} == cols


async def test_card_sessions_columns(v4db):
    cols = await _columns(v4db.conn, "card_sessions")
    assert {"card_id", "session_id", "position_id", "indexes", "created_at"} == cols
