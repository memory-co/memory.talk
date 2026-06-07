"""GET /v3/sync/status — LanceDB health sub-block (issue #4 §6.6).

The existing test_sync.py covers watcher / endpoint / index-completion
fields. These pin the ``index.lance`` block specifically — the field
list is meant to flag EMFILE / fragment-pile / fd-budget risk *before*
search starts 500-ing, so we lock in the contract.
"""
from __future__ import annotations
import pytest


pytestmark = pytest.mark.asyncio


async def test_status_includes_lance_health_block(client):
    r = await client.get("/v3/sync/status")
    body = r.json()
    assert "index" in body
    lance = body["index"].get("lance")
    assert lance is not None, body["index"]
    for key in (
        "pending_vector_rows", "last_flush_at", "last_flush_error",
        "flush_count_since_boot",
        "last_compaction_at", "last_compaction_error",
        "emfile_recoveries_since_boot", "last_emfile_at",
        "fd_soft_limit", "fd_hard_limit",
    ):
        assert key in lance, f"missing {key} in lance health: {lance}"


async def test_lance_health_emfile_counter_reflects_recoveries(app, client, monkeypatch):
    """Drive a fake EMFILE → recovery → assert the counter advanced
    in the sync/status payload."""
    from memorytalk.searchbase import Doc, Query
    from memorytalk.searchbase.local import index as index_mod
    from memorytalk.service.searchbase_schema import ROUNDS

    searchbase = app.state.searchbase
    await searchbase.upsert(ROUNDS, [
        Doc(id="sess-x:1", text="hi",
            fields={"session_id": "sess-x", "idx": 1, "role": "human"}),
    ])

    state = {"fails": 1}
    orig = index_mod._run_hybrid

    async def flaky(table, *a, **kw):
        if state["fails"] > 0:
            state["fails"] -= 1
            raise RuntimeError(
                "lance error: LanceError(IO): Too many open files (os error 24)"
            )
        return await orig(table, *a, **kw)

    monkeypatch.setattr(index_mod, "_run_hybrid", flaky)
    before = (await client.get("/v3/sync/status")).json()["index"]["lance"]
    await searchbase.search(ROUNDS, Query(text="", top_k=5))
    after = (await client.get("/v3/sync/status")).json()["index"]["lance"]
    assert after["emfile_recoveries_since_boot"] == before["emfile_recoveries_since_boot"] + 1
    assert after["last_emfile_at"] is not None


async def test_lance_health_fd_limits_populated_on_unix(client):
    """resource.getrlimit is available on Linux + macOS; tests run there.
    Confirm the fields surface non-null integers."""
    body = (await client.get("/v3/sync/status")).json()
    lance = body["index"]["lance"]
    # Both can be RLIM_INFINITY (very large int) but never None on Unix.
    assert isinstance(lance["fd_soft_limit"], int)
    assert isinstance(lance["fd_hard_limit"], int)
    assert lance["fd_soft_limit"] > 0
