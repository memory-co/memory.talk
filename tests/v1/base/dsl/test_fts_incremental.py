"""Regression: FTS index must absorb rows appended after the initial build.

LanceDB native FTS leaves appended rows in `num_unindexed_rows` until
`optimize()` is called. `ensure_fts_index` must handle that, so that after
many imports the search still sees all matching rows — not just the first
indexed batch.
"""
from __future__ import annotations

from memory_talk.storage.lancedb import LanceStore


def test_ensure_fts_absorbs_appended_sessions(tmp_path):
    store = LanceStore(tmp_path, dim=4)

    # First session + initial index build.
    store.add_session("s0", "LanceDB baseline reference")
    store.ensure_fts_index(LanceStore.SESSIONS)

    # Many more appends (simulating repeated sync imports).
    for i in range(1, 40):
        store.add_session(f"s{i}", f"session {i} payload LanceDB")
        store.ensure_fts_index(LanceStore.SESSIONS)

    # Every session's text has "LanceDB" — we should be able to retrieve them all.
    hits = store.fts_search_sessions("LanceDB", whitelist=None, top_k=100)
    ids = {h["session_id"] for h in hits}
    assert len(ids) == 40, f"expected 40 hits, got {len(ids)}; missing: {set(f's{i}' for i in range(40)) - ids}"


def test_ensure_fts_absorbs_appended_cards(tmp_path):
    store = LanceStore(tmp_path, dim=4)

    # Initial card + index build.
    store.add("c0", "LanceDB baseline", [0.1, 0.2, 0.3, 0.4])
    store.ensure_fts_index(LanceStore.CARDS)

    # Many appends.
    for i in range(1, 30):
        store.add(f"c{i}", f"card {i} LanceDB details", [0.1, 0.2, 0.3, 0.4])
        store.ensure_fts_index(LanceStore.CARDS)

    hits = store.hybrid_search_cards(
        vector=[0.1, 0.2, 0.3, 0.4],
        text="LanceDB",
        whitelist=None,
        top_k=50,
    )
    ids = {h["card_id"] for h in hits}
    # All 30 cards should be reachable via the hybrid path.
    assert len(ids) == 30, f"expected 30 hits, got {len(ids)}"
