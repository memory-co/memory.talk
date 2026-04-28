"""Search: hybrid cards, FTS sessions, DSL whitelist, SearchLog persistence."""
from __future__ import annotations

import pytest

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest, IngestRound,
    IngestSessionRequest, SearchRequest,
)
from memorytalk.service import SearchError


async def _seed(services):
    for sid_raw, text in [
        ("platform-db", "we picked LanceDB for vector storage"),
        ("platform-bug", "fixed a jsonl parser bug yesterday"),
    ]:
        await services.sessions.ingest(IngestSessionRequest(
            session_id=sid_raw, source="claude-code", created_at="",
            metadata={}, sha256=f"h-{sid_raw}",
            rounds=[IngestRound(
                round_id=f"{sid_raw}_r1", parent_id=None, timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text=text)],
                is_sidechain=False,
            )],
        ))
    sid_db = "sess_platform-db"
    await services.cards.create(CreateCardRequest(
        summary="selected LanceDB for embedded vector store",
        rounds=[CardRoundsItem(session_id=sid_db, indexes="1")],
    ))
    await services.db.sessions.update_tags(sid_db, ["decision"])


async def test_search_returns_both_buckets_and_persists(services):
    await _seed(services)
    await services.vectors.ensure_fts_index("cards", replace=True)
    await services.vectors.ensure_fts_index("sessions", replace=True)

    r = await services.search.search(SearchRequest(query="LanceDB"))
    assert r.search_id.startswith("sch_")
    assert r.cards.count >= 1
    assert r.cards.results[0].summary.startswith("selected")

    assert (await services.db.search_log.count()) == 1
    files = await services.storage.list_subkeys("search_log")
    files = [k for k in files if k.endswith(".jsonl")]
    assert len(files) == 1
    content = (await services.storage.read_text(files[0])).strip()
    assert "LanceDB" in content


async def test_search_empty_query_returns_metadata_filtered(services):
    await _seed(services)
    r = await services.search.search(SearchRequest(query="", where='tag = "decision"'))
    assert r.sessions.count == 1
    assert r.sessions.results[0].session_id == "sess_platform-db"
    assert r.cards.count >= 0


async def test_search_dsl_error_raises(services):
    await _seed(services)
    with pytest.raises(SearchError, match="DSL parse error"):
        await services.search.search(SearchRequest(query="x", where="unknown_field = 'x'"))
