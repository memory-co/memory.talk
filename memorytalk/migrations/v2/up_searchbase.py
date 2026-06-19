"""v2 upgrade: searchbase (LanceDB) — no changes from v1.

explore is SQLite-only (no new collections, no embedding changes), so the
v1 → v2 searchbase delta is empty. The file exists because the runner
expects an ``up_searchbase`` per version.
"""
from __future__ import annotations

from memorytalk.searchbase import AdminBackend


async def run(admin: AdminBackend, *, data_root=None) -> None:
    return  # no searchbase schema change in v2
