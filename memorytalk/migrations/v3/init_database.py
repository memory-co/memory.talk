"""v3 fresh-install: SQLite schema snapshot.

This is what a brand-new ``memory.db`` looks like at v3. The runner
calls :func:`run` on the empty database when there is no prior
install detected. This is the v2 schema with the card subsystem renamed
to insight and the reviews table omitted.

The DDL is split into :data:`TABLES` and :data:`INDEXES` so the
upgrade path (``up_database``) can sequence them around additive
ALTERs — an index over a column added by ALTER would fail if it ran
before the ALTER.
"""
from __future__ import annotations

import aiosqlite

# ``TABLES`` is run first so every v3 table exists; ``INDEXES`` runs after.
# Ordering inside ``TABLES`` preserves FK declarations
# (``insight_stats`` → ``insights``).
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
        last_index_attempted_at TEXT,
        last_round_update_time  TEXT
    )
    """,

    # ── explores ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS explores (
        explore_id            TEXT PRIMARY KEY,
        dir_path              TEXT NOT NULL,
        divider_at            TEXT NOT NULL,
        entrypoint_session_id TEXT,
        created_at            TEXT NOT NULL,
        note                  TEXT
    )
    """,

    # ── insights (renamed from cards) ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS insights (
        card_id     TEXT PRIMARY KEY,
        insight     TEXT NOT NULL,
        rounds      TEXT NOT NULL DEFAULT '[]',
        tags        TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL,
        explore_id  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_stats (
        card_id         TEXT PRIMARY KEY,
        review_up       INTEGER NOT NULL DEFAULT 0,
        review_down     INTEGER NOT NULL DEFAULT 0,
        review_neutral  INTEGER NOT NULL DEFAULT 0,
        review_count    INTEGER NOT NULL DEFAULT 0,
        read_count      INTEGER NOT NULL DEFAULT 0,
        updated_at      TEXT NOT NULL,
        FOREIGN KEY (card_id) REFERENCES insights(card_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_source_cards (
        card_id         TEXT NOT NULL,
        seq             INTEGER NOT NULL,
        source_card_id  TEXT NOT NULL,
        relation        TEXT NOT NULL,
        PRIMARY KEY (card_id, seq)
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
    "CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_insight_source ON insight_source_cards(source_card_id)",
    "CREATE INDEX IF NOT EXISTS idx_insights_explore ON insights(explore_id)",
    "CREATE INDEX IF NOT EXISTS idx_explores_created ON explores(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_recall_event_session_ts "
    "ON recall_event(session_id, ts DESC)",
    "CREATE INDEX IF NOT EXISTS idx_search_log_created ON search_log(created_at)",
]


async def run(conn: aiosqlite.Connection, *, data_root=None) -> None:
    """Apply the v3 snapshot to ``conn``. Commits at the end."""
    for stmt in TABLES:
        await conn.execute(stmt)
    for stmt in INDEXES:
        await conn.execute(stmt)
    await conn.commit()
