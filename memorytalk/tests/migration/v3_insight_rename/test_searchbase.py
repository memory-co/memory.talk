"""v3 searchbase — rename cards collection → insights + rewrite ids. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.searchbase import Doc, Query
from memorytalk.migrations.v3 import up_searchbase as v3_up_sb


async def test_v3_up_searchbase_renames_cards_to_insights(backend):
    admin = backend.admin()
    if "cards" not in await admin.list_collections():
        await admin.create_collection("cards", {"fields": {}})
    await v3_up_sb.run(admin, data_root=None)
    cols = await admin.list_collections()
    assert "insights" in cols and "cards" not in cols


async def test_v3_up_searchbase_idempotent(backend):
    admin = backend.admin()
    await v3_up_sb.run(admin, data_root=None)
    await v3_up_sb.run(admin, data_root=None)  # second run no-ops (cards already gone)


async def test_v3_up_searchbase_rewrites_row_ids(backend):
    """A card_<ulid> row becomes insight_<ulid> with its vector preserved."""
    await backend.upsert("cards", [Doc(id="card_x", text="hello forum", fields={})])
    admin = backend.admin()
    await v3_up_sb.run(admin, data_root=None)
    hits = await backend.search("insights", Query(text="hello", top_k=5))
    ids = {h.id for h in hits}
    assert "insight_x" in ids
    assert "card_x" not in ids


async def test_v3_up_searchbase_rewrite_idempotent(backend):
    await backend.upsert("cards", [Doc(id="card_y", text="beta", fields={})])
    admin = backend.admin()
    await v3_up_sb.run(admin, data_root=None)
    await v3_up_sb.run(admin, data_root=None)  # rows already insight_ → no-op
    hits = await backend.search("insights", Query(text="beta", top_k=5))
    assert {h.id for h in hits} == {"insight_y"}
