"""SQLite schema for v3. All DDL in one place; idempotent init_schema().

Optimization notes vs v2:
- ``cards`` table drops ``expires_at`` (v3 has no TTL).
- ``card_stats`` is a new table (six counters per card; updated on review /
  read / recall).
- ``card_source_cards`` is a new table (replaces v2's ``links``).
- ``reviews`` is a new table.
- ``links`` / ``tags`` / ``recall_hit`` tables are gone.
- ``ingest_log`` is a new table (one row per session, holds sha256 +
  last_ingest — moved out of the v2 ``sessions.synced_at`` field so the
  sync watcher can update it without rewriting the session row).
"""
from __future__ import annotations

import aiosqlite


DDL = [
    # ── sessions ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id   TEXT PRIMARY KEY,        -- always 'sess_<...>'
        source       TEXT NOT NULL,           -- 'claude-code' / 'codex' / ...
        cwd          TEXT,                    -- = metadata.cwd; explore namespace key
        created_at   TEXT NOT NULL,
        synced_at    TEXT NOT NULL,
        metadata     TEXT NOT NULL DEFAULT '{}',
        round_count  INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions(cwd)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at)",
    # Round content lives in two places:
    # - jsonl on disk (full structure; source of truth for `read`)
    # - LanceDB rounds table (text + vector; serves FTS + semantic search)
    #
    # The SQL layer keeps only the small bits needed for the ingest-merge
    # protocol — looking up (session_id, round_id) to spot overwrites and
    # to skip already-stored content. No `content`, no `text` here.
    """
    CREATE TABLE IF NOT EXISTS rounds_index (
        session_id    TEXT NOT NULL,
        round_id      TEXT NOT NULL,
        idx           INTEGER NOT NULL,        -- 1-based, gap-free per session
        content_hash  TEXT NOT NULL,           -- detects platform overwrites
        PRIMARY KEY (session_id, round_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rounds_index_idx ON rounds_index(session_id, idx)",
    """
    CREATE TABLE IF NOT EXISTS ingest_log (
        session_id   TEXT PRIMARY KEY,
        sha256       TEXT NOT NULL,
        last_ingest  TEXT NOT NULL
    )
    """,

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
    """Create all v3 tables if missing. Idempotent."""
    for stmt in DDL:
        await conn.execute(stmt)
    await conn.commit()
