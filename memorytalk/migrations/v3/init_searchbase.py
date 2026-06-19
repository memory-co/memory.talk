"""v3 fresh-install: searchbase (LanceDB) snapshot AS OF v4.

= the v2 collections (insights / rounds — the v3 rename added no new
LanceDB collections, it's a SQLite-side rename) PLUS the two new v4
collections ``cards`` (issue embedding) and ``positions`` (claim
embedding). Delegates to v2's snapshot then layers the v4 collections on
top so the two never drift.
"""
from __future__ import annotations

from memorytalk.migrations.v2 import init_searchbase as v2_init
from memorytalk.service.searchbase_schema import SCHEMAS, V4_CARDS, V4_POSITIONS


async def run(admin, *, data_root=None) -> None:
    await v2_init.run(admin, data_root=data_root)
    await admin.create_collection(V4_CARDS, SCHEMAS[V4_CARDS])
    await admin.create_collection(V4_POSITIONS, SCHEMAS[V4_POSITIONS])
