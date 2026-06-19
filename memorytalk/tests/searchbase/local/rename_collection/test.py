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


async def test_rename_drops_empty_new_placeholder(backend):
    """Boot eagerly creates a declared ``new`` collection, so the rename
    target may already exist EMPTY. The rename must drop that placeholder
    and carry ``old``'s rows across (regression: catch-up left the old
    embeddings orphaned because the rename no-op'd)."""
    admin = backend.admin()
    await admin.create_collection("cards2", {"fields": {}})
    await backend.upsert("cards2", [Doc(id="card_1", text="hello", fields={})])
    await admin.create_collection("insights", {"fields": {}})  # empty placeholder
    await admin.rename_collection("cards2", "insights")
    cols = await admin.list_collections()
    assert "insights" in cols and "cards2" not in cols
    assert await backend.count("insights") == 1   # old rows carried over


async def test_rename_refuses_nonempty_new(backend):
    """If ``new`` already holds real rows, the rename is a no-op — never
    clobber data."""
    admin = backend.admin()
    await admin.create_collection("cards2", {"fields": {}})
    await backend.upsert("cards2", [Doc(id="card_1", text="from old", fields={})])
    await admin.create_collection("insights", {"fields": {}})
    await backend.upsert("insights", [Doc(id="ins_1", text="real data", fields={})])
    await admin.rename_collection("cards2", "insights")
    cols = await admin.list_collections()
    assert "insights" in cols and "cards2" in cols   # both untouched
    assert await backend.count("insights") == 1      # real data preserved
