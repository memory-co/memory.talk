"""v4 searchbase — create cards (issue) + positions (claim) collections. See README.md."""
from __future__ import annotations

from memorytalk.migrations.v4 import up_searchbase as v4_up_sb
from memorytalk.migrations.v4 import init_searchbase as v4_init_sb


async def test_v4_up_searchbase_creates_collections(backend):
    admin = backend.admin()
    await v4_up_sb.run(admin, data_root=None)
    cols = set(await admin.list_collections())
    assert {"cards", "positions"} <= cols
    # post-v3 collections still present
    assert "insights" in cols


async def test_v4_up_searchbase_idempotent(backend):
    admin = backend.admin()
    await v4_up_sb.run(admin, data_root=None)
    await v4_up_sb.run(admin, data_root=None)   # second run no-ops
    cols = set(await admin.list_collections())
    assert {"cards", "positions"} <= cols


async def test_v4_init_searchbase_has_all(backend):
    admin = backend.admin()
    await v4_init_sb.run(admin, data_root=None)
    cols = set(await admin.list_collections())
    assert {"insights", "rounds", "cards", "positions"} <= cols
