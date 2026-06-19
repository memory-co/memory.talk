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
    """Insert a card + stats directly into the store, then index it."""
    from memorytalk.searchbase import Doc
    from memorytalk.service.searchbase_schema import INSIGHTS, cap_text

    db = app.state.db
    searchbase = app.state.searchbase
    now = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    await db.cards.insert(card_id, insight, [], now)
    await db.cards.init_stats(card_id, now)
    if up or down or neutral:
        await db.conn.execute(
            "UPDATE card_stats SET review_up = ?, review_down = ?, "
            "review_neutral = ?, review_count = ?, updated_at = ? "
            "WHERE card_id = ?",
            (up, down, neutral, up + down + neutral, now, card_id),
        )
        await db.conn.commit()
    for _ in range(reads):
        await db.cards.bump_read(card_id, now)
    if searchbase is not None:
        await searchbase.upsert(INSIGHTS, [
            Doc(id=card_id, text=cap_text(insight), fields={}),
        ])


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


# ────────── 0.8.x: default formula is pure relevance ──────────

class TestPureRelevanceDefault:
    """Regression net for the vvp-ai class of bug (report-v7).

    Before 0.8.x the default ``ranking_formula`` mixed in
    ``+ 0.02 * log(read_count + 1)``, which could lift a weakly-matched
    high-read card above a strongly-matched zero-read card. The
    default is now ``"relevance"`` — these tests pin that change."""

    async def test_strong_relevance_beats_high_read_weak_relevance(self, app):
        """Direct service-level test: with the default formula
        (``relevance``), a candidate with higher raw relevance must
        outrank one with lower relevance regardless of read_count.

        Driven through ``SearchService._score`` rather than the LanceDB
        path so the assertion doesn't depend on dummy-embedder vector
        noise — this is specifically a regression net for the formula
        change (issue #4 v7 / vvp-ai case)."""
        svc = app.state.search
        strong = {"relevance": 0.033, "read_count": 0, "review_up": 0,
                  "review_down": 0, "review_neutral": 0, "review_count": 0,
                  "recall_count": 0, "created_at": "2026-05-29T00:00:00Z"}
        weak_but_read = {"relevance": 0.013, "read_count": 5, "review_up": 0,
                         "review_down": 0, "review_neutral": 0,
                         "review_count": 0, "recall_count": 0,
                         "created_at": "2026-05-29T00:00:00Z"}
        # With ``settings.search.ranking_formula = "relevance"`` (the
        # 0.8.x default), score == relevance — the high-read card
        # cannot lift past the strong match.
        assert svc._score(strong, kind="card") > svc._score(weak_but_read, kind="card")

    async def test_response_carries_mode_search(self, client):
        r = await client.post("/v3/search", json={"query": "anything"})
        body = r.json()
        assert body["mode"] == "search"
        assert body["session_id"] is None


# ────────── 0.8.x: --recall debug mode ──────────

class TestRecallMode:
    async def test_recall_mode_excludes_session_results(self, app, client):
        """Recall is cards-only by definition (matches RecallService)."""
        await _ingest(client, "rec-1", "sha1", [
            _round("r1", "human", "alpha topic only in session"),
        ])
        await _seed_card(
            app, card_id="card_01RECA", insight="alpha topic card",
        )
        r = await client.post(
            "/v3/search",
            json={"query": "alpha topic", "recall_mode": True, "top_k": 10},
        )
        body = r.json()
        assert body["mode"] == "recall"
        types = {it["type"] for it in body["results"]}
        assert types == {"card"} or types == set()  # no session results

    async def test_recall_mode_ignores_ranking_formula(self, app, client, monkeypatch):
        """Even if the user has customized ranking_formula to include
        forum signals, recall mode must NOT apply it — by-definition
        recall ranking is raw relevance only."""
        # Customize formula to one that would change order: heavy
        # boost on reads. Then recall mode should ignore it.
        from memorytalk.util.formula import compile_formula
        custom = compile_formula("relevance + 10 * read_count")
        app.state.search._formula = custom
        # Card A: weak relevance (no query token), high reads.
        # Card B: strong relevance (contains query), zero reads.
        await _seed_card(
            app, card_id="card_01RM_A", insight="unrelated content", reads=5,
        )
        await _seed_card(
            app, card_id="card_01RM_B", insight="distinctword relevant insight",
        )
        # Normal search would prefer A (10 * 5 reads). Recall mode
        # must prefer B (pure relevance).
        r = await client.post(
            "/v3/search",
            json={"query": "distinctword", "recall_mode": True, "top_k": 5},
        )
        ranks = [it.get("card_id") for it in r.json()["results"] if it["type"] == "card"]
        # B must be present and either alone or ranked above A.
        assert "card_01RM_B" in ranks
        if "card_01RM_A" in ranks:
            assert ranks.index("card_01RM_B") < ranks.index("card_01RM_A"), ranks

    async def test_recall_mode_dedups_against_session(self, app, client):
        """``recall_session_id`` filters out cards already returned in
        that session's ``recall_event`` history (0.9.0: derived via
        json_each, no separate dedup table)."""
        await _seed_card(
            app, card_id="card_01DD_A", insight="alpha alpha alpha",
        )
        await _seed_card(
            app, card_id="card_01DD_B", insight="alpha beta gamma",
        )
        # Mark card A as already recalled for sess-xyz by inserting a
        # synthetic recall_event row.
        await app.state.db.recall.insert_event(
            event_id="evt_test_seed",
            session_id="sess-xyz",
            prompt="seed",
            ts="2026-05-29T00:00:00Z",
            returned_card_ids=["card_01DD_A"],
            skipped_card_ids=[],
        )
        r = await client.post("/v3/search", json={
            "query": "alpha", "recall_mode": True,
            "recall_session_id": "sess-xyz", "top_k": 10,
        })
        body = r.json()
        ids = [it.get("card_id") for it in body["results"] if it["type"] == "card"]
        assert "card_01DD_A" not in ids
        assert "card_01DD_B" in ids
        assert body["session_id"] == "sess-xyz"

    async def test_recall_mode_does_not_bump_recall_count(self, app, client):
        """``--recall`` is read-only — derived recall_count must not move."""
        await _seed_card(
            app, card_id="card_01NB_X", insight="no-bump query",
        )
        counts_before = await app.state.db.recall.recall_counts(["card_01NB_X"])
        await client.post("/v3/search", json={
            "query": "no-bump", "recall_mode": True,
            "recall_session_id": "sess-some", "top_k": 10,
        })
        counts_after = await app.state.db.recall.recall_counts(["card_01NB_X"])
        assert counts_after == counts_before, (
            "search --recall must NOT write recall_event"
        )

    async def test_recall_mode_does_not_write_recall_event(self, app, client):
        """And the recall_event table must stay untouched — otherwise
        next call would silently filter the same card out."""
        await _seed_card(
            app, card_id="card_01NL_X", insight="no-log content",
        )
        await client.post("/v3/search", json={
            "query": "no-log", "recall_mode": True,
            "recall_session_id": "sess-none", "top_k": 10,
        })
        already = await app.state.db.recall.already_recalled(
            "sess-none", ["card_01NL_X"],
        )
        assert "card_01NL_X" not in already


# ────────── 0.8.x: search_log mode column ──────────

class TestAuditMode:
    async def test_search_log_mode_search_for_normal_query(self, app, client):
        await _seed_card(app, card_id="card_01LM_S", insight="mode search row")
        await client.post("/v3/search", json={"query": "mode search"})
        async with app.state.db.conn.execute(
            "SELECT mode FROM search_log ORDER BY created_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        assert row[0] == "search"

    async def test_search_log_mode_recall_for_recall_query(self, app, client):
        await _seed_card(app, card_id="card_01LM_R", insight="mode recall row")
        await client.post("/v3/search", json={
            "query": "mode recall", "recall_mode": True,
        })
        async with app.state.db.conn.execute(
            "SELECT mode FROM search_log ORDER BY created_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        assert row[0] == "recall"
