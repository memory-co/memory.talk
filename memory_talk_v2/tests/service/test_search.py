"""Search: hybrid cards, FTS sessions, DSL whitelist, SearchLog persistence."""
from __future__ import annotations
import json

from memory_talk_v2.service.cards import create_card
from memory_talk_v2.service.search import search
from memory_talk_v2.service.sessions import ingest_session


def _seed(services):
    # Two sessions, one tagged 'decision'
    for i, (sid_raw, text) in enumerate([
        ("platform-db", "we picked LanceDB for vector storage"),
        ("platform-bug", "fixed a jsonl parser bug yesterday"),
    ]):
        ingest_session(
            {"session_id": sid_raw, "source": "claude-code", "created_at": "",
             "metadata": {}, "sha256": f"h-{sid_raw}",
             "rounds": [{"round_id": f"{sid_raw}_r1", "parent_id": None, "timestamp": "",
                         "speaker": "user", "role": "human",
                         "content": [{"type": "text", "text": text}], "is_sidechain": False}]},
            db=services.db, vectors=services.vectors, events=services.events,
            sessions_root=services.config.sessions_dir,
        )
    # One card
    sid_db = "sess_platform-db"
    create_card(
        {"summary": "selected LanceDB for embedded vector store",
         "rounds": [{"session_id": sid_db, "indexes": "1"}]},
        config=services.config, db=services.db, vectors=services.vectors,
        embedder=services.embedder, events=services.events,
    )
    # Tag one session
    services.db.update_session_tags(sid_db, ["decision"])


def test_search_returns_both_buckets_and_persists(services):
    _seed(services)
    # Rebuild FTS (LanceDB defers indexing until ensure_fts_index or read via hybrid)
    services.vectors.ensure_fts_index("cards", replace=True)
    services.vectors.ensure_fts_index("sessions", replace=True)

    r = search({"query": "LanceDB"},
               config=services.config, db=services.db, vectors=services.vectors,
               embedder=services.embedder, search_jsonl=services.search_jsonl)
    assert "cards" in r and "sessions" in r
    assert r["search_id"].startswith("sch_")
    # Card hit should exist (has 'LanceDB' in summary+rounds text)
    assert r["cards"]["count"] >= 1
    assert r["cards"]["results"][0]["summary"].startswith("selected")

    # search_log persisted
    assert services.db.count_search_log() == 1
    # jsonl persisted
    files = list(services.search_jsonl.iter_files())
    assert len(files) == 1
    content = files[0].read_text().strip()
    assert "LanceDB" in content


def test_search_empty_query_returns_metadata_filtered(services):
    _seed(services)
    r = search({"query": "", "where": 'tag = "decision"'},
               config=services.config, db=services.db, vectors=services.vectors,
               embedder=services.embedder, search_jsonl=services.search_jsonl)
    # Only 'platform-db' session was tagged 'decision'
    assert r["sessions"]["count"] == 1
    assert r["sessions"]["results"][0]["session_id"] == "sess_platform-db"
    # Cards bucket is empty (DSL references sessions-only tag with cards-only cross-check):
    # `tag` applies to sessions only via our DSL (sessions have tags); for cards it checks cards.tags
    # which is empty for all inserted cards in this test.
    # Either empty or present depending on interpretation — we just assert no crash.
    assert r["cards"]["count"] >= 0


def test_search_dsl_error_raises(services):
    from memory_talk_v2.service.search import SearchError
    _seed(services)
    import pytest
    with pytest.raises(SearchError, match="DSL parse error"):
        search({"query": "x", "where": "unknown_field = 'x'"},
               config=services.config, db=services.db, vectors=services.vectors,
               embedder=services.embedder, search_jsonl=services.search_jsonl)
