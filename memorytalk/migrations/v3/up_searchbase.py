"""v3 upgrade: rename the cards LanceDB collection → insights."""
from __future__ import annotations

from memorytalk.searchbase import AdminBackend


async def run(admin: AdminBackend, *, data_root=None) -> None:
    await admin.rename_collection("cards", "insights")  # idempotent
