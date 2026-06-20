"""v4 card subsystem SQLite schema (DDL constants).

Single source of truth for the 8 v4 tables. Reused by
``migrations/v3/{init,up}_database.py`` and by tests. SQLite is a derived
index over file-canonical truth (card.json / positions/p<n>.json /
links/l<n>.json / marks/m<n>.yaml); **no FOREIGN KEY** anywhere (this
repo's hard rule -- dangling refs are tolerated). Counters
(position_count / link_count / up/down/neutral/review_count) are
redundant caches maintained on write. credence is NOT a column -- the
service computes it at read/sort time.

Addressing (card-scoped / session-scoped subordinate ids, no global id):
``positions`` = ``<card_id>#p<n>``, ``card_links`` = ``<card_id>#l<n>``,
``session_marks`` = ``<session_id>#m<n>``.
"""
from __future__ import annotations

import aiosqlite

V4_TABLES: list[str] = [
    """CREATE TABLE IF NOT EXISTS cards (
        card_id        TEXT PRIMARY KEY,
        issue          TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        position_count INTEGER NOT NULL DEFAULT 0,
        link_count     INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS positions (
        card_id        TEXT NOT NULL,
        position       TEXT NOT NULL,
        claim          TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        up_count       INTEGER NOT NULL DEFAULT 0,
        down_count     INTEGER NOT NULL DEFAULT 0,
        neutral_count  INTEGER NOT NULL DEFAULT 0,
        review_count   INTEGER NOT NULL DEFAULT 0,
        scope          TEXT NOT NULL DEFAULT '',
        forked_from    TEXT,
        PRIMARY KEY (card_id, position)
    )""",
    """CREATE TABLE IF NOT EXISTS reviews (
        review_id   TEXT PRIMARY KEY,
        card_id     TEXT NOT NULL,
        target      TEXT NOT NULL,
        target_kind TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        indexes     TEXT NOT NULL,
        argument    INTEGER NOT NULL,
        comment     TEXT,
        created_at  TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS card_links (
        card_id       TEXT NOT NULL,
        link          TEXT NOT NULL,
        type          TEXT NOT NULL,
        target_id     TEXT NOT NULL,
        target_type   TEXT NOT NULL,
        claim         TEXT NOT NULL,
        up_count      INTEGER NOT NULL DEFAULT 0,
        down_count    INTEGER NOT NULL DEFAULT 0,
        neutral_count INTEGER NOT NULL DEFAULT 0,
        review_count  INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL,
        PRIMARY KEY (card_id, link),
        UNIQUE (card_id, type, target_id)
    )""",
    """CREATE TABLE IF NOT EXISTS card_sessions (
        card_id     TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        mark        TEXT NOT NULL,
        indexes     TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (card_id, session_id, mark)
    )""",
    """CREATE TABLE IF NOT EXISTS position_sessions (
        card_id     TEXT NOT NULL,
        position    TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        indexes     TEXT NOT NULL,
        mark        TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL,
        PRIMARY KEY (card_id, position, session_id, mark)
    )""",
    """CREATE TABLE IF NOT EXISTS link_sessions (
        card_id     TEXT NOT NULL,
        link        TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        indexes     TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (card_id, link, session_id)
    )""",
    """CREATE TABLE IF NOT EXISTS session_marks (
        session_id  TEXT NOT NULL,
        mark        TEXT NOT NULL,
        last_index  INTEGER NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (session_id, mark)
    )""",
]

# Expected column set per v4 table, kept adjacent to ``V4_TABLES`` as the
# drift detector's reference. A table that EXISTS with a different column
# set is a drifted/older derived index (e.g. a preview build's
# ``card_sessions`` with ``position_id`` instead of ``mark``, or
# ``positions`` with ``forked_from_position_id`` instead of ``forked_from``)
# and gets dropped + recreated by ``create_card_schema``. Asserted to match
# the DDL in tests so the two can't silently drift apart.
V4_EXPECTED_COLUMNS: dict[str, frozenset[str]] = {
    "cards": frozenset({
        "card_id", "issue", "created_at", "position_count", "link_count",
    }),
    "positions": frozenset({
        "card_id", "position", "claim", "created_at", "up_count",
        "down_count", "neutral_count", "review_count", "scope", "forked_from",
    }),
    "reviews": frozenset({
        "review_id", "card_id", "target", "target_kind", "session_id",
        "indexes", "argument", "comment", "created_at",
    }),
    "card_links": frozenset({
        "card_id", "link", "type", "target_id", "target_type", "claim",
        "up_count", "down_count", "neutral_count", "review_count",
        "created_at",
    }),
    "card_sessions": frozenset({
        "card_id", "session_id", "mark", "indexes", "created_at",
    }),
    "position_sessions": frozenset({
        "card_id", "position", "session_id", "indexes", "mark", "created_at",
    }),
    "link_sessions": frozenset({
        "card_id", "link", "session_id", "indexes", "created_at",
    }),
    "session_marks": frozenset({
        "session_id", "mark", "last_index", "created_at",
    }),
}

V4_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_v4_cards_created ON cards(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_v4_reviews_target ON reviews(card_id, target, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_v4_reviews_card ON reviews(card_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_links_target ON card_links(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_csess_session ON card_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_csess_mark ON card_sessions(session_id, mark)",
    "CREATE INDEX IF NOT EXISTS idx_v4_psess_session ON position_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_lsess_session ON link_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_smarks_session ON session_marks(session_id)",
]


async def _table_columns(conn: aiosqlite.Connection, table: str) -> set[str]:
    """Actual column names of ``table``, or empty set if it doesn't exist."""
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return {row[1] for row in rows}


async def _drop_drifted_tables(conn: aiosqlite.Connection) -> None:
    """Drop any v4 table that EXISTS but whose column set ≠ the current
    schema's expected set. These tables are derived indexes over
    file-canonical truth, so dropping a drifted/older one is safe — the
    subsequent CREATE rebuilds it with the right structure. A table that
    already matches (or doesn't exist) is left untouched, keeping re-runs
    idempotent. Scoped to the 8 v4 tables this module owns, so a
    freshly-renamed v3 ``insights`` table is never touched."""
    for table, expected in V4_EXPECTED_COLUMNS.items():
        actual = await _table_columns(conn, table)
        if actual and actual != set(expected):
            await conn.execute(f"DROP TABLE {table}")


async def create_card_schema(conn: aiosqlite.Connection) -> None:
    """Create all v4 tables + indexes (idempotent, drift-tolerant).

    Before creating, drop any pre-existing v4 table whose columns drifted
    from the current schema (e.g. left by an earlier preview build) — a
    plain ``CREATE TABLE IF NOT EXISTS`` would skip it, then an index on a
    new column would crash with ``no such column``."""
    await _drop_drifted_tables(conn)
    for stmt in V4_TABLES:
        await conn.execute(stmt)
    for stmt in V4_INDEXES:
        await conn.execute(stmt)
    await conn.commit()
