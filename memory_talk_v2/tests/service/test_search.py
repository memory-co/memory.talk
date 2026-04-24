"""Search: hybrid cards, FTS sessions, DSL whitelist, SearchLog persistence."""
from __future__ import annotations

import pytest

from memory_talk_v2.service import SearchError


def _seed(services):
    for sid_raw, text in [
        ("platform-db", "we picked LanceDB for vector storage"),
        ("platform-bug", "fixed a jsonl parser bug yesterday"),
    ]:
        services.sessions.ingest(
            {"session_id": sid_raw, "source": "claude-code", "created_at": "",
             "metadata": {}, "sha256": f"h-{sid_raw}",
             "rounds": [{"round_id": f"{sid_raw}_r1", "parent_id": None, "timestamp": "",
                         "speaker": "user", "role": "human",
                         "content": [{"type": "text", "text": text}], "is_sidechain": False}]},
        )
    sid_db = "sess_platform-db"
    services.cards.create(
        {"summary": "selected LanceDB for embedded vector store",
         "rounds": [{"session_id": sid_db, "indexes": "1"}]},
    )
    services.db.update_session_tags(sid_db, ["decision"])


def test_search_returns_both_buckets_and_persists(services):
    _seed(services)
    services.vectors.ensure_fts_index("cards", replace=True)
    services.vectors.ensure_fts_index("sessions", replace=True)

    r = services.search.search({"query": "LanceDB"})
    assert "cards" in r and "sessions" in r
    assert r["search_id"].startswith("sch_")
    assert r["cards"]["count"] >= 1
    assert r["cards"]["results"][0]["summary"].startswith("selected")

    assert services.db.count_search_log() == 1
    files = list(services.search_jsonl.iter_files())
    assert len(files) == 1
    content = files[0].read_text().strip()
    assert "LanceDB" in content


def test_search_empty_query_returns_metadata_filtered(services):
    _seed(services)
    r = services.search.search({"query": "", "where": 'tag = "decision"'})
    assert r["sessions"]["count"] == 1
    assert r["sessions"]["results"][0]["session_id"] == "sess_platform-db"
    assert r["cards"]["count"] >= 0


def test_search_dsl_error_raises(services):
    _seed(services)
    with pytest.raises(SearchError, match="DSL parse error"):
        services.search.search({"query": "x", "where": "unknown_field = 'x'"})
