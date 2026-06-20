"""create_card_schema is drift-tolerant — an UPGRADE from an older/preview
v4 DB (drifted columns) must succeed, not crash on an index over a new
column. See issue #6.
"""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.repository.card_schema import (
    V4_EXPECTED_COLUMNS,
    V4_INDEXES,
    V4_TABLES,
    create_card_schema,
)


async def _columns(conn, table) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        return {row[1] for row in await cur.fetchall()}


def _ddl_columns(stmt: str) -> set[str]:
    """Pull column names out of a ``CREATE TABLE`` DDL body — the first
    token of each line inside the parens that isn't a table constraint."""
    body = stmt[stmt.index("(") + 1: stmt.rindex(")")]
    cols: set[str] = set()
    depth = 0
    for line in body.splitlines():
        # Track paren depth so a multi-column ``PRIMARY KEY (a, b)`` /
        # ``UNIQUE (...)`` clause's inner tokens aren't read as columns.
        line = line.strip()
        if not line:
            continue
        first = line.split()[0]
        if depth == 0 and first.upper() not in {"PRIMARY", "UNIQUE", "FOREIGN", "CHECK"}:
            cols.add(first)
        depth += line.count("(") - line.count(")")
    return cols


def _table_name(stmt: str) -> str:
    return stmt.split("IF NOT EXISTS")[1].split("(")[0].strip()


# ────────── expected-columns map ⇔ DDL ──────────

def test_expected_columns_match_ddl():
    """The hand-maintained ``V4_EXPECTED_COLUMNS`` map can't silently
    drift from the DDL it mirrors."""
    from_ddl = {_table_name(stmt): _ddl_columns(stmt) for stmt in V4_TABLES}
    assert set(V4_EXPECTED_COLUMNS) == set(from_ddl)
    for table, expected in V4_EXPECTED_COLUMNS.items():
        assert set(expected) == from_ddl[table], table


# ────────── drift tolerance ──────────

async def _make_drifted_db(path) -> None:
    """Seed a DB with OLD-schema ``card_sessions`` (``position_id`` instead
    of ``mark``) and OLD ``positions`` (``forked_from_position_id``)."""
    conn = await aiosqlite.connect(path)
    await conn.execute(
        """CREATE TABLE card_sessions (
            card_id     TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            position_id TEXT,
            indexes     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )"""
    )
    await conn.execute(
        """CREATE TABLE positions (
            card_id                  TEXT NOT NULL,
            position                 TEXT NOT NULL,
            claim                    TEXT NOT NULL,
            created_at               TEXT NOT NULL,
            forked_from_position_id  TEXT,
            PRIMARY KEY (card_id, position)
        )"""
    )
    await conn.commit()
    await conn.close()


async def test_upgrade_from_drifted_v4_succeeds(tmp_path):
    path = tmp_path / "drift.db"
    await _make_drifted_db(path)

    conn = await aiosqlite.connect(path)
    # Must not raise ``no such column: mark`` / ``forked_from``.
    await create_card_schema(conn)

    csess = await _columns(conn, "card_sessions")
    assert "mark" in csess
    assert "position_id" not in csess

    positions = await _columns(conn, "positions")
    assert "forked_from" in positions
    assert "forked_from_position_id" not in positions

    # All indexes applied (the failing one was idx_v4_csess_mark).
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_v4_%'"
    ) as cur:
        idx_names = {r[0] for r in await cur.fetchall()}
    assert "idx_v4_csess_mark" in idx_names
    assert len(idx_names) == len(V4_INDEXES)
    await conn.close()


async def test_second_run_is_noop(tmp_path):
    """A DB whose v4 tables already match must be untouched (no drop)."""
    path = tmp_path / "fresh.db"
    conn = await aiosqlite.connect(path)
    await create_card_schema(conn)

    # Stamp a row; if the second run dropped+recreated, the row vanishes.
    await conn.execute(
        "INSERT INTO cards (card_id, issue, created_at) VALUES (?,?,?)",
        ("card_x", "an issue", "2026-01-01T00:00:00Z"),
    )
    await conn.commit()

    await create_card_schema(conn)  # idempotent re-run

    async with conn.execute("SELECT count(*) FROM cards") as cur:
        (n,) = await cur.fetchone()
    assert n == 1  # not dropped
    await conn.close()


async def test_freshly_renamed_insights_untouched(tmp_path):
    """``create_card_schema`` is scoped to the 8 v4 tables — a v3
    ``insights`` table (renamed just before this runs) is not in scope
    and must survive untouched even though its columns differ from any
    v4 table."""
    path = tmp_path / "insights.db"
    conn = await aiosqlite.connect(path)
    await conn.execute(
        "CREATE TABLE insights (card_id TEXT PRIMARY KEY, body TEXT)"
    )
    await conn.execute(
        "INSERT INTO insights (card_id, body) VALUES (?,?)",
        ("insight_1", "kept"),
    )
    await conn.commit()

    await create_card_schema(conn)

    async with conn.execute("SELECT count(*) FROM insights") as cur:
        (n,) = await cur.fetchone()
    assert n == 1
    await conn.close()
