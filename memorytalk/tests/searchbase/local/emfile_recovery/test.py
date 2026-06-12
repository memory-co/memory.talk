"""emfile_recovery — search 路径撞 EMFILE 后的自愈反应链.
See README.md.
"""
from __future__ import annotations

import asyncio

from memorytalk.searchbase import Doc
from memorytalk.searchbase.local.maintenance import Maintenance


# ────────── recovery 推进 counter ──────────

async def test_recover_from_emfile_advances_counter(index):
    m = Maintenance(index, compact_interval_seconds=10.0)
    index.attach_maintenance(m)
    before = m.emfile_recoveries
    await m.recover_from_emfile()
    assert m.emfile_recoveries == before + 1
    assert m.last_emfile_at_iso is not None


# ────────── 并发 caller 复用一次 recovery ──────────

async def test_recover_from_emfile_concurrent_callers_share_work(index):
    """Two concurrent recoveries must net out to exactly one cycle —
    the generation counter is what protects us from N concurrent
    EMFILEs spinning N redundant reconnects."""
    m = Maintenance(index, compact_interval_seconds=10.0)
    index.attach_maintenance(m)
    before = m.emfile_recoveries
    await asyncio.gather(
        m.recover_from_emfile(),
        m.recover_from_emfile(),
    )
    assert m.emfile_recoveries == before + 1


# ────────── 真的换了 LanceDB 连接(不只是 compact) ──────────

async def test_recover_from_emfile_reconnects_lancedb(index):
    """The reconnect is what actually frees the held reader fds —
    after recovery the connection object must be a fresh one."""
    m = Maintenance(index, compact_interval_seconds=10.0)
    index.attach_maintenance(m)
    db_before = index.db
    await m.recover_from_emfile()
    assert index.db is not db_before


# ────────── known set 在 recovery 开头自刷新 ──────────

async def test_emfile_recovery_repopulates_collections(backend):
    """Recovery compacts every known collection. If the known-set is
    stale/empty (e.g. a read-only boot whose initial list_tables
    failed), recovery must re-list tables so it actually compacts
    something instead of looping over nothing."""
    await backend.upsert("cards", [Doc(id="c1", text="x")])
    index = backend._index
    index._collections.clear()
    await backend._maintenance.recover_from_emfile()
    assert "cards" in index.known_collections
