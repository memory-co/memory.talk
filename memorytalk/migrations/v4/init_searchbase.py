"""v4 fresh-install: searchbase snapshot = v3 (insights/rounds) + the two
v4 collections (cards/positions).
"""
from __future__ import annotations

from memorytalk.migrations.v3 import init_searchbase as v3_init
from memorytalk.service.searchbase_schema import (
    SCHEMAS, V4_CARDS, V4_POSITIONS,
)


async def run(admin, *, data_root=None) -> None:
    await v3_init.run(admin, data_root=data_root)   # insights / rounds
    await admin.create_collection(V4_CARDS, SCHEMAS[V4_CARDS])
    await admin.create_collection(V4_POSITIONS, SCHEMAS[V4_POSITIONS])
