"""v1 upgrade: bring a 0.8.x SQLite database up to v1.

Two responsibilities:

1. Make sure every v1 table exists (CREATE IF NOT EXISTS — covers
   tables added through 0.8.x like ``recall_event``, ``card_stats``).
2. Apply the additive ALTERs for columns that landed between 0.6.x
   and 0.8.x. Each step is gated on a PRAGMA probe so re-runs are
   no-ops.

History note (so future-you knows what each step is for):

- ``sessions.last_round_id`` — added when sync rewrote round tracking
  to use platform round_ids end-to-end.
- ``sessions.indexed_round_count`` + ``last_index_error`` +
  ``last_index_attempted_at`` — added 0.6.1 after the DashScope 10-batch
  silent-corruption bug, so we can tell which sessions are degraded.
- ``sessions.location`` + ``location_label`` — added 0.7.x for
  multi-endpoint sync. Both filled from the session_id loc_code.
- ``sessions.tags`` / ``cards.tags`` — 0.8.x user-side kv tags.
- ``search_log.mode`` — 0.8.x ``search --recall`` audit-replay split.
- Legacy ``rounds_index`` + ``ingest_log`` are dropped (their state
  moved to a separate sync.db / the sessions table itself).
"""
from __future__ import annotations

import aiosqlite

from memorytalk.migrations.v1.init_database import INDEXES, TABLES


async def run(conn: aiosqlite.Connection) -> None:
    """Bring ``conn`` up to v1. Safe to run repeatedly."""
    # 1. Snapshot CREATE TABLEs — guarantees every table is present.
    #    Indexes come LATER, after the additive ALTERs add the columns
    #    some of those indexes reference.
    for stmt in TABLES:
        await conn.execute(stmt)

    # 2. Additive ALTERs against pre-existing rows.
    sessions_cols = await _cols(conn, "sessions")
    if "last_round_id" not in sessions_cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN last_round_id TEXT"
        )
    if "last_round_update_time" not in sessions_cols:
        # explore's prior/posterior split keys off this. Backfilled from
        # rounds.jsonl in step (below) on the upgrade path.
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN last_round_update_time TEXT"
        )
    if "indexed_round_count" not in sessions_cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN indexed_round_count "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "last_index_error" not in sessions_cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN last_index_error TEXT"
        )
    if "last_index_attempted_at" not in sessions_cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN last_index_attempted_at TEXT"
        )
    if "location" not in sessions_cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN location "
            "TEXT NOT NULL DEFAULT ''"
        )
    if "location_label" not in sessions_cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN location_label TEXT"
        )
    if "tags" not in sessions_cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN tags "
            "TEXT NOT NULL DEFAULT '{}'"
        )

    cards_cols = await _cols(conn, "cards")
    if "tags" not in cards_cols:
        await conn.execute(
            "ALTER TABLE cards ADD COLUMN tags TEXT NOT NULL DEFAULT '{}'"
        )
    if "explore_id" not in cards_cols:
        await conn.execute("ALTER TABLE cards ADD COLUMN explore_id TEXT")

    reviews_cols = await _cols(conn, "reviews")
    if reviews_cols and "explore_id" not in reviews_cols:
        await conn.execute("ALTER TABLE reviews ADD COLUMN explore_id TEXT")

    slog_cols = await _cols(conn, "search_log")
    if slog_cols and "mode" not in slog_cols:
        await conn.execute(
            "ALTER TABLE search_log ADD COLUMN "
            "mode TEXT NOT NULL DEFAULT 'search'"
        )

    # 3. Legacy ``rounds_index`` carries last_round_id we need to copy
    #    over before dropping it.
    if await _table_exists(conn, "rounds_index"):
        await conn.execute(
            "UPDATE sessions SET last_round_id = ("
            "  SELECT round_id FROM rounds_index ri "
            "  WHERE ri.session_id = sessions.session_id "
            "  ORDER BY idx DESC LIMIT 1"
            ") WHERE last_round_id IS NULL"
        )
        await conn.execute("DROP TABLE rounds_index")

    # 4. Drop the legacy sync-checkpoint table (state moved to sync.db).
    await conn.execute("DROP TABLE IF EXISTS ingest_log")

    # 5. 0.9 dropped ``recall_log`` in favor of ``recall_event`` +
    #    canonical ``recall.jsonl`` files. History isn't migrated — the
    #    old table never stored prompts, so a faithful ``RecallEvent``
    #    row can't be reconstructed. Recall popularity starts from
    #    empty post-upgrade and rebuilds as users issue new recalls.
    await conn.execute("DROP INDEX IF EXISTS idx_recall_log_session")
    await conn.execute("DROP TABLE IF EXISTS recall_log")

    # 6. 0.9 dropped ``card_stats.recall_count`` (popularity is now
    #    derived from ``recall_event`` on read). SQLite 3.35+ supports
    #    DROP COLUMN; Python 3.10+ ships well above that.
    stats_cols = await _cols(conn, "card_stats")
    if "recall_count" in stats_cols:
        await conn.execute(
            "ALTER TABLE card_stats DROP COLUMN recall_count"
        )

    # 7. Indexes — every column they reference exists now.
    for stmt in INDEXES:
        await conn.execute(stmt)

    await conn.commit()


async def _cols(conn: aiosqlite.Connection, table: str) -> set[str]:
    """Return the column set for ``table``, or empty if missing."""
    async with conn.execute(f"PRAGMA table_info({table})") as cursor:
        return {row[1] for row in await cursor.fetchall()}


async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ) as cursor:
        return (await cursor.fetchone()) is not None
