"""v4 card subsystem SQLite schema (DDL constants).

Single source of truth for the 5 v4 tables. Reused by
``migrations/v4/init_database.py`` and by tests. SQLite is a derived
index over file-canonical truth (card.json / positions/<pid>.json);
**no FOREIGN KEY** anywhere (this repo's hard rule -- dangling refs are
tolerated). Counters (position_count / link_count / up/down/neutral/
review_count) are redundant caches maintained on write. credence is NOT
a column -- the service computes it at read/sort time.
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
        position_id             TEXT PRIMARY KEY,
        card_id                 TEXT NOT NULL,
        claim                   TEXT NOT NULL,
        created_at              TEXT NOT NULL,
        up_count                INTEGER NOT NULL DEFAULT 0,
        down_count              INTEGER NOT NULL DEFAULT 0,
        neutral_count           INTEGER NOT NULL DEFAULT 0,
        review_count            INTEGER NOT NULL DEFAULT 0,
        scope                   TEXT NOT NULL DEFAULT '',
        forked_from_position_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS reviews (
        review_id   TEXT PRIMARY KEY,
        position_id TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        indexes     TEXT NOT NULL,
        argument    INTEGER NOT NULL,
        comment     TEXT,
        created_at  TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS card_links (
        card_id     TEXT NOT NULL,
        type        TEXT NOT NULL,
        target_id   TEXT NOT NULL,
        target_type TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (card_id, type, target_id)
    )""",
    """CREATE TABLE IF NOT EXISTS card_sessions (
        card_id     TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        position_id TEXT,
        indexes     TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (card_id, session_id, indexes)
    )""",
]

V4_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_v4_cards_created ON cards(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_v4_positions_card ON positions(card_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_reviews_position ON reviews(position_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_v4_links_target ON card_links(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_csess_session ON card_sessions(session_id)",
]


async def create_v4_schema(conn: aiosqlite.Connection) -> None:
    """Create all v4 tables + indexes (idempotent)."""
    for stmt in V4_TABLES:
        await conn.execute(stmt)
    for stmt in V4_INDEXES:
        await conn.execute(stmt)
    await conn.commit()
