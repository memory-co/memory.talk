"""v1 fresh-install: SQLite schema snapshot.

This is what a brand-new ``memory.db`` looks like at v1. The runner
calls :func:`run` on the empty database when there is no prior
install detected (no on-disk vectors, no state file).

The DDL is split into :data:`TABLES` and :data:`INDEXES` so the
upgrade path (``up_database``) can sequence them around additive
ALTERs — an index over a column added by ALTER would fail if it ran
before the ALTER.
"""
from __future__ import annotations

import aiosqlite

# ``TABLES`` is run first so every v1 table exists; ``INDEXES`` runs
# AFTER any additive ALTERs in the upgrade path (so e.g. the
# sessions(source, location) index doesn't try to reference a column
# that the legacy table is still missing). Ordering inside ``TABLES``
# preserves FK declarations (``card_stats`` → ``cards``).
TABLES: list[str] = [
    # ── sessions ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id              TEXT PRIMARY KEY,
        source                  TEXT NOT NULL,
        location                TEXT NOT NULL DEFAULT '',
        location_label          TEXT,
        cwd                     TEXT,
        created_at              TEXT NOT NULL,
        synced_at               TEXT NOT NULL,
        metadata                TEXT NOT NULL DEFAULT '{}',
        tags                    TEXT NOT NULL DEFAULT '{}',
        round_count             INTEGER NOT NULL DEFAULT 0,
        last_round_id           TEXT,
        indexed_round_count     INTEGER NOT NULL DEFAULT 0,
        last_index_error        TEXT,
        last_index_attempted_at TEXT
    )
    """,

    # ── cards ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS cards (
        card_id     TEXT PRIMARY KEY,
        insight     TEXT NOT NULL,
        rounds      TEXT NOT NULL DEFAULT '[]',
        tags        TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS card_stats (
        card_id         TEXT PRIMARY KEY,
        review_up       INTEGER NOT NULL DEFAULT 0,
        review_down     INTEGER NOT NULL DEFAULT 0,
        review_neutral  INTEGER NOT NULL DEFAULT 0,
        review_count    INTEGER NOT NULL DEFAULT 0,
        read_count      INTEGER NOT NULL DEFAULT 0,
        updated_at      TEXT NOT NULL,
        FOREIGN KEY (card_id) REFERENCES cards(card_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS card_source_cards (
        card_id         TEXT NOT NULL,
        seq             INTEGER NOT NULL,
        source_card_id  TEXT NOT NULL,
        relation        TEXT NOT NULL,
        PRIMARY KEY (card_id, seq)
    )
    """,

    # ── reviews ──────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS reviews (
        review_id   TEXT PRIMARY KEY,
        card_id     TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        indexes     TEXT NOT NULL,
        score       INTEGER NOT NULL,
        comment     TEXT,
        created_at  TEXT NOT NULL,
        FOREIGN KEY (card_id) REFERENCES cards(card_id)
    )
    """,

    # ── recall_event ─────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS recall_event (
        event_id      TEXT PRIMARY KEY,
        session_id    TEXT NOT NULL,
        prompt        TEXT NOT NULL,
        ts            TEXT NOT NULL,
        returned_ids  TEXT NOT NULL,
        skipped_ids   TEXT NOT NULL
    )
    """,

    # ── search_log ───────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS search_log (
        search_id      TEXT PRIMARY KEY,
        query          TEXT NOT NULL,
        where_dsl      TEXT,
        top_k          INTEGER NOT NULL,
        mode           TEXT NOT NULL DEFAULT 'search',
        created_at     TEXT NOT NULL,
        response_json  TEXT NOT NULL
    )
    """,
]


INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions(cwd)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_endpoint ON sessions(source, location)",
    "CREATE INDEX IF NOT EXISTS idx_cards_created ON cards(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_csc_source ON card_source_cards(source_card_id)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_card ON reviews(card_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_session ON reviews(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_recall_event_session_ts "
    "ON recall_event(session_id, ts DESC)",
    "CREATE INDEX IF NOT EXISTS idx_search_log_created ON search_log(created_at)",
]


async def run(conn: aiosqlite.Connection, *, data_root=None) -> None:
    """Apply the v1 snapshot to ``conn``. Commits at the end."""
    for stmt in TABLES:
        await conn.execute(stmt)
    for stmt in INDEXES:
        await conn.execute(stmt)
    await conn.commit()
