"""POST /v3/search — unified ranking, DSL filtering, audit, edge cases."""
from __future__ import annotations
import datetime as _dt
import json

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _ingest(client, sid: str, sha: str, rounds: list[dict]) -> dict:
    # ``sha`` parameter is no longer used by the cursor-based API; kept
    # in the signature so the call sites in this file don't all need to
    # change. It's effectively a label.
    del sha
    r = await ingest_session(client, sid, rounds=rounds)
    r.raise_for_status()
    return r.json()


def _round(rid: str, role: str, text: str) -> dict:
    return {
        "round_id": rid, "role": role,
        "content": [{"type": "text", "text": text}],
    }


async def _seed_card(app, *, card_id: str, insight: str,
                     up: int = 0, down: int = 0, neutral: int = 0,
                     reads: int = 0) -> None:
    """Insert a card + stats directly into the store, then push to LanceDB."""
    db = app.state.db
    vectors = app.state.vectors
    embedder = app.state.embedder
    now = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    await db.cards.insert(card_id, insight, [], now)
    await db.cards.init_stats(card_id, now)
    for _ in range(up):
        await db.cards.bump_review(card_id, 1, now)
    for _ in range(down):
        await db.cards.bump_review(card_id, -1, now)
    for _ in range(neutral):
        await db.cards.bump_review(card_id, 0, now)
    for _ in range(reads):
        await db.cards.bump_read(card_id, now)
    if vectors and embedder:
        vec = await embedder.embed_one(insight)
        await vectors.add_card(card_id, insight, vec)


# ────────── core paths ──────────

class TestCore:
    async def test_returns_mixed_card_and_session_results(self, app, client):
        await _ingest(client, "search-1", "sha1", [
            _round("r1", "human", "I want to use LanceDB for vector storage"),
            _round("r2", "assistant", "LanceDB is good — embedded, zero deps"),
        ])
        await _seed_card(app, card_id="card_lance", insight="LanceDB is embedded vector db")

        r = await client.post("/v3/search", json={"query": "LanceDB"})
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "LanceDB"
        assert body["count"] > 0
        types = [item["type"] for item in body["results"]]
        assert "card" in types
        assert "session" in types

    async def test_highlights_keywords_in_card_insight(self, app, client):
        await _seed_card(app, card_id="card_hl", insight="LanceDB is good for embeddings")
        r = await client.post("/v3/search", json={"query": "LanceDB"})
        card = next(it for it in r.json()["results"] if it["type"] == "card")
        assert "**LanceDB**" in card["insight"]

    async def test_session_hits_have_context_windows(self, client):
        """Hit's context_before / context_after come from neighboring rounds."""
        await _ingest(client, "ctx-1", "sha1", [
            _round("r1", "human", "we need to pick a vector db"),
            _round("r2", "assistant", "I recommend LanceDB"),
            _round("r3", "human", "ok lets use LanceDB then"),
        ])
        r = await client.post("/v3/search", json={"query": "LanceDB"})
        session = next(it for it in r.json()["results"] if it["type"] == "session")
        assert session["hit_count"] >= 1
        hit = session["hits"][0]
        if hit["index"] == 2:
            assert hit["context_before"]["index"] == 1
            assert "vector db" in hit["context_before"]["text"]
            assert hit["context_after"]["index"] == 3
        elif hit["index"] == 3:
            assert hit["context_before"]["index"] == 2
            assert "LanceDB" in hit["context_before"]["text"]

    async def test_session_aggregates_multiple_hits(self, client):
        """One session with multiple round hits → ONE session result with hits[] aggregated."""
        await _ingest(client, "multi-hit", "sha1", [
            _round("r1", "human", "lancedb intro"),
            _round("r2", "assistant", "lancedb is fast"),
            _round("r3", "human", "tell me more about lancedb"),
            _round("r4", "assistant", "lancedb is embedded"),
        ])
        r = await client.post("/v3/search", json={"query": "lancedb"})
        sessions = [it for it in r.json()["results"] if it["type"] == "session"]
        assert len(sessions) == 1
        s = sessions[0]
        assert s["hit_count"] >= 3
        assert s["hits_shown"] <= 3

    async def test_assigns_rank_1_based(self, app, client):
        await _ingest(client, "rank-1", "sha1", [_round("r1", "human", "rankme")])
        await _seed_card(app, card_id="card_rank", insight="rankme too")
        r = await client.post("/v3/search", json={"query": "rankme"})
        ranks = [it["rank"] for it in r.json()["results"]]
        assert ranks == list(range(1, len(ranks) + 1))

    async def test_empty_results_for_unrelated_query(self, client):
        r = await client.post("/v3/search", json={"query": "completely-unrelated-zzz"})
        body = r.json()
        assert body["count"] == 0
        assert body["results"] == []


# ────────── DSL ──────────

class TestDSL:
    async def test_review_count_zero_returns_only_cards(self, app, client):
        await _ingest(client, "filter-1", "sha1", [_round("r1", "human", "anything about lancedb")])
        await _seed_card(app, card_id="card_new", insight="lancedb fresh card")
        await _seed_card(app, card_id="card_reviewed", insight="lancedb reviewed", up=2)
        r = await client.post("/v3/search", json={
            "query": "lancedb",
            "where": "review_count = 0",
        })
        body = r.json()
        types = {it["type"] for it in body["results"]}
        assert types == {"card"}
        ids = [it["card_id"] for it in body["results"]]
        assert "card_new" in ids
        assert "card_reviewed" not in ids

    async def test_source_narrows_to_sessions(self, app, client):
        await _ingest(client, "src-1", "sha1", [_round("r1", "human", "lancedb here")])
        await _seed_card(app, card_id="card_x", insight="lancedb extra")
        r = await client.post("/v3/search", json={
            "query": "lancedb",
            "where": "source = \"claude-code\"",
        })
        types = {it["type"] for it in r.json()["results"]}
        assert types == {"session"}

    async def test_type_filter(self, app, client):
        await _ingest(client, "type-1", "sha1", [_round("r1", "human", "lancedb t")])
        await _seed_card(app, card_id="card_t", insight="lancedb t")
        r = await client.post("/v3/search", json={
            "query": "lancedb",
            "where": "type = \"card\"",
        })
        assert {it["type"] for it in r.json()["results"]} == {"card"}

    async def test_empty_query_with_dsl_only(self, app, client):
        """Gap fill: ``--where 'review_count = 0'`` with empty query should
        still surface matching cards. v2 had ``test_search_empty_query_returns_metadata_filtered``."""
        await _seed_card(app, card_id="card_a", insight="a")
        await _seed_card(app, card_id="card_b", insight="b", up=3)
        r = await client.post("/v3/search", json={
            "query": "",
            "where": "review_count = 0",
        })
        # Even with no query, the DSL filter narrows to cards-only and only
        # the un-reviewed one passes.
        body = r.json()
        ids = [it["card_id"] for it in body["results"] if it["type"] == "card"]
        assert "card_a" in ids
        assert "card_b" not in ids

    async def test_bad_dsl_returns_400(self, client):
        r = await client.post("/v3/search", json={
            "query": "x", "where": "no_such_field = 1",
        })
        assert r.status_code == 400
        assert "unknown field" in r.json()["detail"]


# ────────── audit log ──────────

class TestAudit:
    async def test_writes_search_log_sqlite(self, app, client):
        await _ingest(client, "log-1", "sha1", [_round("r1", "human", "log topic")])
        await client.post("/v3/search", json={"query": "log topic"})
        n = await app.state.db.search_log.count()
        assert n == 1

    async def test_writes_search_log_jsonl_mirror(self, app, client):
        """Gap fill: docs say SearchLog also lands in ``logs/search/<UTC>.jsonl``."""
        await _ingest(client, "log-2", "sha1", [_round("r1", "human", "audit topic")])
        await client.post("/v3/search", json={"query": "audit topic"})

        search_log_dir = app.state.config.search_log_dir
        files = list(search_log_dir.glob("*.jsonl"))
        assert files, "expected at least one logs/search/<date>.jsonl"
        # Last line of any file contains a record whose query echoes the request.
        for f in files:
            lines = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            if any(rec["query"] == "audit topic" for rec in lines):
                return
        pytest.fail("audit topic record not found in jsonl mirror")
