"""v3 upgrade: rename card subsystem → insight + drop unused reviews.

Renames the 3 card tables, drops the (unused) reviews table + its indexes,
renames indexes, moves the file-canonical dir cards/ → insights/, AND
rewrites the id VALUES ``card_<ulid>`` → ``insight_<ulid>`` (the ``card_``
prefix is now owned by the v4 question-graph subsystem; insight ids carry
their own ``insight_`` prefix). All transform logic lives here
(migrations/), per the migration design.

Column NAMES stay ``card_id`` / ``source_card_id`` — only the VALUES are
rewritten; the API/CLI/schema surface presents them as ``insight_id``.
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
    # 4. Rewrite id VALUES card_<ulid> → insight_<ulid>. Idempotent:
    # guarded on ``LIKE 'card_%'`` so a re-run (where values already
    # carry ``insight_``) is a no-op. Only VALUES change — column names
    # stay ``card_id`` / ``source_card_id``.
    await _rewrite_ids(conn)
    await conn.commit()
    # 5. File-canonical dir move cards/ → insights/ + per-insight leaf
    # dir rename card_<ulid> → insight_<ulid> (idempotent).
    if data_root is not None:
        old, new = Path(data_root) / "cards", Path(data_root) / "insights"
        if old.exists() and not new.exists():
            old.rename(new)
        _rewrite_file_dirs(new)


async def _rewrite_ids(conn) -> None:
    """Rewrite ``card_<ulid>`` → ``insight_<ulid>`` across SQLite.

    The bucket key (first 2 chars after the prefix) is unchanged by the
    swap, so this is a pure value rewrite. ``substr(col, 6)`` drops the
    5-char ``card_`` prefix; ``'insight_' || ...`` re-prefixes.
    ``recall_event`` id arrays are JSON text referencing only insights
    at v3-migration time, so a plain string replace inside the JSON is
    safe."""
    names = await _tables(conn)
    rewrites = [
        ("insights", "card_id"),
        ("insight_stats", "card_id"),
        ("insight_source_cards", "card_id"),
        ("insight_source_cards", "source_card_id"),
    ]
    for table, col in rewrites:
        if table not in names:
            continue
        await conn.execute(
            f"UPDATE {table} SET {col} = 'insight_' || substr({col}, 6) "
            f"WHERE {col} LIKE 'card_%'"
        )
    # recall_event id arrays are JSON text; rewrite the prefix inside.
    if "recall_event" in names:
        for col in ("returned_ids", "skipped_ids"):
            await conn.execute(
                f"UPDATE recall_event "
                f"SET {col} = REPLACE({col}, '\"card_', '\"insight_') "
                f"WHERE {col} LIKE '%\"card\\_%' ESCAPE '\\'"
            )


def _rewrite_file_dirs(insights_root: Path) -> None:
    """Rename each ``insights/<bucket>/card_<ulid>`` leaf dir to
    ``insight_<ulid>``. Bucket dirs are unchanged. Idempotent — only
    ``card_``-prefixed leaves are touched."""
    if not insights_root.exists():
        return
    for bucket in insights_root.iterdir():
        if not bucket.is_dir():
            continue
        for leaf in bucket.iterdir():
            if leaf.is_dir() and leaf.name.startswith("card_"):
                target = bucket / ("insight_" + leaf.name[len("card_"):])
                if not target.exists():
                    leaf.rename(target)
