"""v3 upgrade: searchbase (LanceDB) — no changes from v2.

The v2 → v3 rename (cards → insight subsystem) is SQLite-only; no
LanceDB collections or embeddings change. The file exists because the
runner expects an ``up_searchbase`` per version.
"""
from __future__ import annotations

from memorytalk.searchbase import AdminBackend


async def run(admin: AdminBackend, *, data_root=None) -> None:
    return  # no searchbase schema change in v3
