"""v2 upgrade: explore subsystem schema (v1 → v2).

Adds the ``explores`` table + the additive explore columns
(``sessions.last_round_update_time``, ``cards.explore_id``,
``reviews.explore_id``) + their indexes. See docs/works/v3/explore.md.

Each step is gated (CREATE IF NOT EXISTS / PRAGMA probe) so re-runs and
partial-failure resumes are no-ops. The ``last_round_update_time``
*backfill* (computing it from rounds.jsonl for existing sessions) is NOT
here — the migration runner has no filesystem handle; it runs at boot,
see ``api/__init__.py`` / ``SessionStore.backfill_last_round_update_time``.
"""
from __future__ import annotations

import aiosqlite


_EXPLORES = """
CREATE TABLE IF NOT EXISTS explores (
    explore_id            TEXT PRIMARY KEY,
    dir_path              TEXT NOT NULL,
    divider_at            TEXT NOT NULL,
    entrypoint_session_id TEXT,
    created_at            TEXT NOT NULL,
    note                  TEXT
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_cards_explore ON cards(explore_id)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_explore ON reviews(explore_id)",
    "CREATE INDEX IF NOT EXISTS idx_explores_created ON explores(created_at)",
]


async def run(conn: aiosqlite.Connection) -> None:
    """Bring ``conn`` from v1 to v2. Safe to run repeatedly."""
    await conn.execute(_EXPLORES)

    if "last_round_update_time" not in await _cols(conn, "sessions"):
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN last_round_update_time TEXT"
        )
    if "explore_id" not in await _cols(conn, "cards"):
        await conn.execute("ALTER TABLE cards ADD COLUMN explore_id TEXT")
    reviews_cols = await _cols(conn, "reviews")
    if reviews_cols and "explore_id" not in reviews_cols:
        await conn.execute("ALTER TABLE reviews ADD COLUMN explore_id TEXT")

    for stmt in _INDEXES:
        await conn.execute(stmt)
    await conn.commit()


async def _cols(conn: aiosqlite.Connection, table: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table})") as cursor:
        return {row[1] for row in await cursor.fetchall()}
