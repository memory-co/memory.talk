"""schema -- v4 DDL creates the 8 tables with the right columns. See README.md."""
from __future__ import annotations


async def _columns(conn, table):
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        return {row["name"] for row in await cur.fetchall()}


async def test_eight_tables_exist(v4db):
    async with v4db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cur:
        names = {r["name"] for r in await cur.fetchall()}
    assert {
        "cards", "positions", "reviews", "card_links", "card_sessions",
        "position_sessions", "link_sessions", "session_marks",
    } <= names


async def test_cards_has_redundant_counters(v4db):
    cols = await _columns(v4db.conn, "cards")
    assert {"card_id", "issue", "created_at", "position_count", "link_count"} == cols


async def test_positions_card_scoped_and_governance(v4db):
    cols = await _columns(v4db.conn, "positions")
    assert {"card_id", "position", "claim", "created_at",
            "up_count", "down_count", "neutral_count", "review_count",
            "scope", "forked_from"} == cols
    assert "position_id" not in cols          # no global id
    assert "forked_from_position_id" not in cols
    assert "credence" not in cols             # credence is computed, never stored


async def test_card_links_governed_with_counts(v4db):
    cols = await _columns(v4db.conn, "card_links")
    assert {"card_id", "link", "type", "target_id", "target_type", "claim",
            "up_count", "down_count", "neutral_count", "review_count",
            "created_at"} == cols
    assert "credence" not in cols


async def test_reviews_columns(v4db):
    cols = await _columns(v4db.conn, "reviews")
    assert {"review_id", "card_id", "target", "target_kind", "session_id",
            "indexes", "argument", "comment", "created_at"} == cols
    assert "position_id" not in cols


async def test_card_sessions_columns(v4db):
    cols = await _columns(v4db.conn, "card_sessions")
    assert {"card_id", "session_id", "mark", "indexes", "created_at"} == cols
    assert "position_id" not in cols


async def test_new_provenance_tables_columns(v4db):
    assert await _columns(v4db.conn, "position_sessions") == {
        "card_id", "position", "session_id", "indexes", "mark", "created_at"}
    assert await _columns(v4db.conn, "link_sessions") == {
        "card_id", "link", "session_id", "indexes", "created_at"}
    assert await _columns(v4db.conn, "session_marks") == {
        "session_id", "mark", "last_index", "created_at"}
