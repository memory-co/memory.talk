"""v4 upgrade: create the v4 LanceDB collections.

``cards`` (issue embedding) + ``positions`` (claim embedding). The
``cards`` name was freed by migration ``v3`` (v3 card collection →
``insights``), so on an in-place upgrade this runs *after* the v3 rename
has vacated it. Idempotent — ``create_collection`` no-ops if the
collection already exists (e.g. boot already ensured it from SCHEMAS).
"""
from __future__ import annotations

from memorytalk.service.searchbase_schema import (
    SCHEMAS, V4_CARDS, V4_POSITIONS,
)


async def run(admin, *, data_root=None) -> None:
    await admin.create_collection(V4_CARDS, SCHEMAS[V4_CARDS])
    await admin.create_collection(V4_POSITIONS, SCHEMAS[V4_POSITIONS])
