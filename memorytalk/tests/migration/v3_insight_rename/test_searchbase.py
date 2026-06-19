"""v3 searchbase — rename cards collection → insights. See README.md."""
from __future__ import annotations

import pytest

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
