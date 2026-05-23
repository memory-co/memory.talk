"""SQLite schema for v3. All DDL in one place; idempotent init_schema().

v3 simplifications vs the historical layout:

- ``cards`` table drops ``expires_at`` (v3 has no TTL).
- ``card_stats`` is a per-card counters table.
- ``card_source_cards`` replaces the v2 ``links`` table.
- ``rounds_index`` / ``ingest_log`` are **gone**: sync state lives in a
  separate ``sync.db`` (see ``repository/sync_checkpoint.py``), and the
  per-session "what's the latest round we've stored" cursor moves to a
  new ``last_round_id`` column on ``sessions``. The ``IngestService``
  now exposes ``append_rounds`` with optimistic-concurrency on that
  cursor, so the per-round content-hash dedup ``rounds_index`` provided
  is no longer needed.
"""
from __future__ import annotations

import aiosqlite


DDL = [
    # ── sessions ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id              TEXT PRIMARY KEY,    -- always 'sess_<...>'
        source                  TEXT NOT NULL,       -- 'claude-code' / 'codex' / ...
        cwd                     TEXT,                -- = metadata.cwd; explore namespace key
        created_at              TEXT NOT NULL,
        synced_at               TEXT NOT NULL,
        metadata                TEXT NOT NULL DEFAULT '{}',
        round_count             INTEGER NOT NULL DEFAULT 0,
        last_round_id           TEXT,                -- platform round_id of round_count'th round
        -- Vector index tracking (lance rounds table)
        -- indexed_round_count < round_count  → degraded, eligible for backfill.
        -- last_index_error / last_index_attempted_at are observability fields:
        -- show the user why a session is stuck and when we last tried.
        indexed_round_count     INTEGER NOT NULL DEFAULT 0,
        last_index_error        TEXT,
        last_index_attempted_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions(cwd)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at)",

    # ── cards ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS cards (
        card_id     TEXT PRIMARY KEY,
        insight     TEXT NOT NULL,
        rounds      TEXT NOT NULL DEFAULT '[]',  -- CardRound[] JSON
        created_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cards_created ON cards(created_at)",
    """
    CREATE TABLE IF NOT EXISTS card_stats (
        card_id         TEXT PRIMARY KEY,
        review_up       INTEGER NOT NULL DEFAULT 0,
        review_down     INTEGER NOT NULL DEFAULT 0,
        review_neutral  INTEGER NOT NULL DEFAULT 0,
        review_count    INTEGER NOT NULL DEFAULT 0,
        read_count      INTEGER NOT NULL DEFAULT 0,
        recall_count    INTEGER NOT NULL DEFAULT 0,
        updated_at      TEXT NOT NULL,
        FOREIGN KEY (card_id) REFERENCES cards(card_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS card_source_cards (
        card_id         TEXT NOT NULL,           -- the card whose source list this row belongs to
        seq             INTEGER NOT NULL,        -- position in source_cards[] for stable ordering
        source_card_id  TEXT NOT NULL,           -- referenced card
        relation        TEXT NOT NULL,           -- 'derives_from' | 'supersedes'
        PRIMARY KEY (card_id, seq)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_csc_source ON card_source_cards(source_card_id)",

    # ── reviews ──────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS reviews (
        review_id   TEXT PRIMARY KEY,
        card_id     TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        indexes     TEXT NOT NULL,             -- raw input string, e.g. '20-25'
        score       INTEGER NOT NULL,          -- -1 / 0 / 1
        comment     TEXT,
        created_at  TEXT NOT NULL,
        FOREIGN KEY (card_id) REFERENCES cards(card_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reviews_card ON reviews(card_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_session ON reviews(session_id)",

    # ── recall_log (in-memory-ish — cleared on rebuild) ──────────────────
    """
    CREATE TABLE IF NOT EXISTS recall_log (
        session_id   TEXT NOT NULL,
        card_id      TEXT NOT NULL,
        recalled_at  TEXT NOT NULL,
        PRIMARY KEY (session_id, card_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_recall_log_session ON recall_log(session_id)",

    # ── search_log (audit) ───────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS search_log (
        search_id      TEXT PRIMARY KEY,
        query          TEXT NOT NULL,
        where_dsl      TEXT,
        top_k          INTEGER NOT NULL,
        created_at     TEXT NOT NULL,
        response_json  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_search_log_created ON search_log(created_at)",
]


async def init_schema(conn: aiosqlite.Connection) -> None:
    """Create all v3 tables if missing, then apply additive migrations
    against pre-existing installs. Idempotent."""
    for stmt in DDL:
        await conn.execute(stmt)
    await _additive_migrations(conn)
    await conn.commit()


async def _additive_migrations(conn: aiosqlite.Connection) -> None:
    """One-shot upgrades for existing DBs. Safe to run on every boot —
    each step checks whether the destination state already exists."""
    # 1. Add ``last_round_id`` column to ``sessions`` if missing.
    async with conn.execute("PRAGMA table_info(sessions)") as cursor:
        cols = {row[1] for row in await cursor.fetchall()}
    if "last_round_id" not in cols:
        await conn.execute("ALTER TABLE sessions ADD COLUMN last_round_id TEXT")

    # 1b. Add vector-index tracking columns (added 0.6.1 after the
    #     DashScope 10-batch silent-corruption bug — without these we
    #     have no way to query "which sessions are degraded"). Existing
    #     rows get ``indexed_round_count=0``, which intentionally puts
    #     them on the backfill backlog at next boot.
    if "indexed_round_count" not in cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN indexed_round_count "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "last_index_error" not in cols:
        await conn.execute("ALTER TABLE sessions ADD COLUMN last_index_error TEXT")
    if "last_index_attempted_at" not in cols:
        await conn.execute("ALTER TABLE sessions ADD COLUMN last_index_attempted_at TEXT")

    # 2. If the legacy ``rounds_index`` table is around, derive
    #    last_round_id from it (max-idx round per session), then drop it.
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rounds_index'"
    ) as cursor:
        has_rounds_index = await cursor.fetchone() is not None
    if has_rounds_index:
        await conn.execute(
            "UPDATE sessions SET last_round_id = ("
            "  SELECT round_id FROM rounds_index ri "
            "  WHERE ri.session_id = sessions.session_id "
            "  ORDER BY idx DESC LIMIT 1"
            ") WHERE last_round_id IS NULL"
        )
        await conn.execute("DROP TABLE rounds_index")

    # 3. Drop the legacy sync-checkpoint table — sync state moved to a
    #    separate ``sync.db`` (see ``repository/sync_checkpoint.py``).
    await conn.execute("DROP TABLE IF EXISTS ingest_log")
