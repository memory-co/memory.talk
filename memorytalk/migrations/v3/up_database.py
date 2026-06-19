"""v3 upgrade: rename card subsystem → insight + drop unused reviews.

Renames the 3 card tables, drops the (unused) reviews table + its indexes,
renames indexes, and moves the file-canonical dir cards/ → insights/.
All transform logic lives here (migrations/), per the migration design.
Keeps card_<ulid> ids (only container names change).
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite


async def _tables(conn) -> set[str]:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


async def run(conn: aiosqlite.Connection, *, data_root: Path | None = None) -> None:
    """v2 → v3. Idempotent."""
    names = await _tables(conn)
    # 1. Drop unused reviews (frees the name for v4) + its indexes.
    await conn.execute("DROP INDEX IF EXISTS idx_reviews_card")
    await conn.execute("DROP INDEX IF EXISTS idx_reviews_session")
    await conn.execute("DROP INDEX IF EXISTS idx_reviews_explore")
    await conn.execute("DROP TABLE IF EXISTS reviews")
    # 2. Rename the 3 card tables → insight* (only if not already done).
    if "cards" in names and "insights" not in names:
        await conn.execute("ALTER TABLE cards RENAME TO insights")
    if "card_stats" in names and "insight_stats" not in names:
        await conn.execute("ALTER TABLE card_stats RENAME TO insight_stats")
    if "card_source_cards" in names and "insight_source_cards" not in names:
        await conn.execute("ALTER TABLE card_source_cards RENAME TO insight_source_cards")
    # 3. Rename indexes (drop old, recreate on the renamed tables).
    await conn.execute("DROP INDEX IF EXISTS idx_cards_created")
    await conn.execute("DROP INDEX IF EXISTS idx_csc_source")
    await conn.execute("DROP INDEX IF EXISTS idx_cards_explore")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at)")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_insight_source ON insight_source_cards(source_card_id)")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_insights_explore ON insights(explore_id)")
    await conn.commit()
    # 4. File-canonical dir move cards/ → insights/ (idempotent).
    if data_root is not None:
        old, new = Path(data_root) / "cards", Path(data_root) / "insights"
        if old.exists() and not new.exists():
            old.rename(new)
