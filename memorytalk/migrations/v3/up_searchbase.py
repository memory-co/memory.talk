"""v3 upgrade: rename the cards LanceDB collection → insights, then
rewrite its row ids ``card_<ulid>`` → ``insight_<ulid>``.

The id rewrite preserves the existing vectors (NO re-embed): we read
every row out of the (already-renamed) ``insights`` table, drop it,
recreate it, and reinsert the rows with rewritten ids. Zero rows → no-op.
Idempotent: rows already carrying ``insight_`` are left untouched.
"""
from __future__ import annotations

from memorytalk.searchbase import AdminBackend


async def run(admin: AdminBackend, *, data_root=None) -> None:
    await admin.rename_collection("cards", "insights")  # idempotent
    await _rewrite_insight_ids(admin)


async def _rewrite_insight_ids(admin: AdminBackend) -> None:
    """Rewrite ``card_<ulid>`` → ``insight_<ulid>`` on every row of the
    ``insights`` collection, preserving vectors. Reaches the underlying
    lancedb table via the admin's CollectionIndex."""
    index = admin._index  # LocalAdminBackend wraps a CollectionIndex
    if not await index._exists("insights"):
        return
    table = await index.db.open_table("insights")
    total = await table.count_rows()
    if total == 0:
        return
    rows = await table.query().limit(total).to_list()
    if not rows:
        return
    if not any(str(r.get("id", "")).startswith("card_") for r in rows):
        return  # already rewritten — idempotent no-op

    rewritten = []
    for r in rows:
        r2 = dict(r)
        rid = str(r2.get("id", ""))
        if rid.startswith("card_"):
            r2["id"] = "insight_" + rid[len("card_"):]
        rewritten.append(r2)

    # Drop + recreate the table, then reinsert with rewritten ids. The
    # schema is preserved by re-adding the same row dicts (vectors and
    # all). Done in-place on the raw lancedb table so we keep the exact
    # existing vector values (no re-embed).
    schema = await table.schema()
    await index.db.drop_table("insights")
    new_table = await index.db.create_table("insights", schema=schema)
    await new_table.add(rewritten)
    index._fts_index_known.discard("insights")
