"""v3 searchbase — rename old cards→insights + rewrite ids, then create the
new v4 cards/positions collections. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.searchbase import Doc, Query
from memorytalk.migrations.v3 import up_searchbase as v3_up_sb


async def test_v3_up_searchbase_renames_cards_and_adds_v4_collections(backend):
    admin = backend.admin()
    if "cards" not in await admin.list_collections():
        await admin.create_collection("cards", {"fields": {}})
    await v3_up_sb.run(admin, data_root=None)
    cols = set(await admin.list_collections())
    # old cards data lives under insights now; the v4 cards/positions
    # collections were (re)created on the freed names.
    assert {"insights", "cards", "positions"} <= cols


async def test_v3_up_searchbase_idempotent(backend):
    admin = backend.admin()
    await v3_up_sb.run(admin, data_root=None)
    await v3_up_sb.run(admin, data_root=None)  # second run no-ops
    cols = set(await admin.list_collections())
    assert {"insights", "cards", "positions"} <= cols


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
