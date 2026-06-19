"""rename_collection -- collection rename keeps rows, frees old name. See README.md."""
from __future__ import annotations

from memorytalk.searchbase._types import Doc


async def test_rename_moves_collection(backend):
    admin = backend.admin()
    await admin.create_collection("cards2", {"fields": {}})
    await backend.upsert("cards2", [Doc(id="card_1", text="hello", fields={})])
    await admin.rename_collection("cards2", "insights")
    cols = await admin.list_collections()
    assert "insights" in cols and "cards2" not in cols
    assert await backend.count("insights") == 1


async def test_rename_idempotent_when_old_absent(backend):
    admin = backend.admin()
    await admin.rename_collection("nonexistent", "whatever")  # no error
