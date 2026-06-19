"""v4 upgrade: searchbase no-op.

v4's LanceDB collections (``cards`` embedding the issue, ``positions``
embedding the claim) land in a later plan; this version is SQLite-only.
"""
from __future__ import annotations


async def run(admin, *, data_root=None) -> None:
    return  # v4 searchbase collections land in a later plan
