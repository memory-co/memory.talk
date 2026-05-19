"""SearchService — POST /v3/search.

Single ranked stream of card + session candidates, ordered by
``settings.search.ranking_formula``. Sessions are aggregated from the
LanceDB rounds table (one row per round); their relevance is a bounded
``1 - prod(1 - s_i)`` over per-round hit scores.

Pipeline:

  1. Parse DSL → predicates + bucket-applicability hints.
  2. LanceDB hybrid search:
       - cards table  → candidate cards with relevance
       - rounds table → candidate hits, grouped by session
  3. Build Candidate objects (cards + sessions) with relevance / stats /
     age_days; apply DSL predicates → filter.
  4. Evaluate ``ranking_formula`` against each candidate's variable dict.
  5. Sort by final score, take top_k, assign rank.
  6. For session candidates: dereference hit-round text from jsonl,
     attach context_before / context_after (also from jsonl).
  7. For card candidates: highlight insight with the query.
  8. Append the full response to ``search_log`` + ``logs/search/<date>.jsonl``.
"""
from __future__ import annotations
import datetime as _dt
import json
import math
from pathlib import Path

from memorytalk.config import Config
from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import (
    CardResult, CardStats, SearchResponse, SessionHit, SessionResult,
)
from memorytalk.util import dsl as dsl_mod
from memorytalk.util.formula import FormulaError, compile_formula
from memorytalk.util.highlight import highlight_keywords, truncate
from memorytalk.util.ids import new_search_id


# Oversample multipliers — pull more candidates than top_k from each
# pipeline so the formula stage has room to rerank across both buckets.
_CARD_OVERSAMPLE = 3
_ROUNDS_OVERSAMPLE = 5
# Per-session hit display limit (search.md约定:每 session 最多展示 3 个窗).
_HITS_PER_SESSION = 3
# Context window: 1 round before + 1 round after the hit.
_CONTEXT_TRUNCATE = 200


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _age_days(created_at_iso: str, now: _dt.datetime | None = None) -> float:
    if not created_at_iso:
        return 0.0
    try:
        # Tolerate both 'Z' suffix and explicit offset.
        s = created_at_iso.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(s)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.UTC)
    now = now or _dt.datetime.now(_dt.UTC)
    return max(0.0, (now - dt).total_seconds() / 86400.0)


def _aggregate_session_relevance(scores: list[float]) -> float:
    """1 - prod(1 - s_i): bounded 'any of them' aggregator.

    Multiple round hits in the same session multiply the chance that
    *some* round of this session matches, with diminishing returns. Maps
    to [0, 1] and never exceeds the strongest single hit by much.
    """
    if not scores:
        return 0.0
    p = 1.0
    for s in scores:
        # Clamp into [0, 1] — RRF scores are normally in this range; defensive
        # in case a provider returns negatives or very large numbers.
        s = max(0.0, min(1.0, s))
        p *= (1.0 - s)
    return 1.0 - p


class SearchService:
    def __init__(
        self,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore | None,
        embedder: Embedder | None,
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.embedder = embedder
        # Compile formula once. If user gave us garbage in settings, fail
        # loudly here so the FastAPI lifespan dies — better than blowing
        # up on the first query at 3am.
        try:
            self._formula = compile_formula(config.settings.search.ranking_formula)
        except FormulaError as e:
            raise FormulaError(
                f"settings.search.ranking_formula is invalid: {e}"
            ) from e

    async def search(
        self, query: str, where: str | None, top_k: int | None,
    ) -> SearchResponse:
        top_k = top_k or self.config.settings.search.default_top_k
        flt = dsl_mod.parse(where or "")

        # ──────── 1. Pull candidates from both buckets ────────
        card_candidates: list[dict] = []
        session_candidates: list[dict] = []

        # Embedding for vector half of hybrid search. Empty query → no
        # vector (relevance comes from a stats-only formula or pure DSL filter).
        qvec: list[float] | None = None
        if query and query.strip() and self.embedder is not None:
            try:
                qvec = await self.embedder.embed_one(query)
            except Exception:
                qvec = None

        if flt.scope_includes("card"):
            card_candidates = await self._collect_card_candidates(query, qvec, top_k)
        if flt.scope_includes("session"):
            session_candidates = await self._collect_session_candidates(query, qvec, top_k)

        # ──────── 2. DSL filter ────────
        card_candidates = [c for c in card_candidates if flt.evaluate(c, "card")]
        session_candidates = [c for c in session_candidates if flt.evaluate(c, "session")]

        # ──────── 3. Score via ranking formula ────────
        for c in card_candidates:
            c["final_score"] = self._score(c, kind="card")
        for c in session_candidates:
            c["final_score"] = self._score(c, kind="session")

        # ──────── 4. Merge + sort + cut ────────
        merged: list[tuple[str, dict]] = (
            [("card", c) for c in card_candidates]
            + [("session", c) for c in session_candidates]
        )
        merged.sort(key=lambda x: x[1]["final_score"], reverse=True)
        merged = merged[:top_k]

        # ──────── 5. Build response objects ────────
        results = []
        # Per-session jsonl cache so we read each jsonl once even if multiple
        # hits land in the same session.
        rounds_cache: dict[str, list[dict]] = {}
        for rank, (kind, c) in enumerate(merged, start=1):
            if kind == "card":
                results.append(self._build_card_result(c, rank, query))
            else:
                results.append(await self._build_session_result(c, rank, query, rounds_cache))

        search_id = new_search_id()
        response = SearchResponse(
            search_id=search_id, query=query, count=len(results), results=results,
        )

        # ──────── 6. Audit log ────────
        await self._log(search_id, query, where, top_k, response)

        return response

    # ──────── candidate builders ────────

    async def _collect_card_candidates(
        self, query: str, qvec: list[float] | None, top_k: int,
    ) -> list[dict]:
        if self.vectors is None:
            return []
        # Make sure FTS index exists before the first query of the process.
        try:
            await self.vectors.ensure_fts_index(self.vectors.CARDS)
        except Exception:
            pass
        hits = await self.vectors.search_cards(
            query=query, vector=qvec, top_k=top_k * _CARD_OVERSAMPLE,
        )
        out: list[dict] = []
        for row in hits:
            card_id = row.get("card_id")
            if not card_id:
                continue
            card_row = await self.db.cards.get(card_id)
            if card_row is None:
                continue  # LanceDB might point at a card that was rolled back
            stats = await self.db.cards.get_stats(card_id)
            out.append({
                "card_id": card_id,
                "insight": card_row["insight"],
                "created_at": card_row["created_at"],
                "relevance": float(row["_score"]),
                "stats": stats,
                # Flatten stats so DSL `where: 'review_count = 0'` works without
                # the predicate having to know about nested dicts.
                **{k: stats.get(k, 0) for k in (
                    "review_up", "review_down", "review_neutral",
                    "review_count", "read_count", "recall_count",
                )},
            })
        return out

    async def _collect_session_candidates(
        self, query: str, qvec: list[float] | None, top_k: int,
    ) -> list[dict]:
        if self.vectors is None:
            return []
        try:
            await self.vectors.ensure_fts_index(self.vectors.ROUNDS)
        except Exception:
            pass
        hits = await self.vectors.search_rounds(
            query=query, vector=qvec, top_k=top_k * _ROUNDS_OVERSAMPLE,
        )
        # Group by session_id.
        by_session: dict[str, list[dict]] = {}
        for row in hits:
            sid = row.get("session_id")
            if not sid:
                continue
            by_session.setdefault(sid, []).append({
                "index": int(row["idx"]),
                "role": row.get("role") or "",
                "score": float(row["_score"]),
            })

        out: list[dict] = []
        for sid, hit_list in by_session.items():
            session_row = await self.db.sessions.get(sid)
            if session_row is None:
                continue
            hit_list.sort(key=lambda h: h["score"], reverse=True)
            relevance = _aggregate_session_relevance([h["score"] for h in hit_list])
            out.append({
                "session_id": sid,
                "source": session_row["source"],
                "created_at": session_row["created_at"],
                "round_count": session_row["round_count"],
                "relevance": relevance,
                "hits": hit_list,
            })
        return out

    # ──────── scoring ────────

    def _score(self, cand: dict, kind: str) -> float:
        # Build the variable namespace the formula sees. Missing stat
        # fields (sessions don't have any) default to 0 inside _eval().
        env = {
            "relevance": float(cand.get("relevance", 0.0)),
            "age_days": _age_days(cand.get("created_at", "")),
        }
        if kind == "card":
            for k in ("review_up", "review_down", "review_neutral",
                      "review_count", "read_count", "recall_count"):
                env[k] = float(cand.get(k, 0))
        # Pad explicit zeros for the session bucket so an author-edited
        # formula that references stats won't NameError on sessions.
        else:
            for k in ("review_up", "review_down", "review_neutral",
                      "review_count", "read_count", "recall_count"):
                env[k] = 0.0
        return self._formula(env)

    # ──────── result builders ────────

    def _build_card_result(self, cand: dict, rank: int, query: str) -> CardResult:
        return CardResult(
            rank=rank,
            score=float(cand["final_score"]),
            card_id=cand["card_id"],
            insight=highlight_keywords(cand["insight"], query),
            stats=CardStats(**cand["stats"]),
        )

    async def _build_session_result(
        self, cand: dict, rank: int, query: str, cache: dict[str, list[dict]],
    ) -> SessionResult:
        sid = cand["session_id"]
        rounds = await self._load_rounds(sid, cache)
        by_idx = {r["idx"]: r for r in rounds}

        hits_shown = cand["hits"][:_HITS_PER_SESSION]
        session_hits: list[SessionHit] = []
        for h in hits_shown:
            cur = by_idx.get(h["index"])
            if cur is None:
                continue
            session_hits.append(SessionHit(
                index=h["index"],
                role=cur.get("role") or h["role"],
                text=highlight_keywords(cur.get("text") or "", query),
                score=float(h["score"]),
                context_before=self._context(by_idx.get(h["index"] - 1), query),
                context_after=self._context(by_idx.get(h["index"] + 1), query),
            ))

        return SessionResult(
            rank=rank,
            score=float(cand["final_score"]),
            session_id=sid,
            source=cand["source"],
            hit_count=len(cand["hits"]),
            hits_shown=len(session_hits),
            hits=session_hits,
        )

    def _context(self, round_dict: dict | None, query: str):
        if round_dict is None:
            return None
        from memorytalk.schemas.search import _SessionHitContext
        text = round_dict.get("text") or ""
        return _SessionHitContext(
            index=round_dict["idx"],
            role=round_dict.get("role") or "",
            text=truncate(highlight_keywords(text, query), limit=_CONTEXT_TRUNCATE),
        )

    async def _load_rounds(self, session_id: str, cache: dict) -> list[dict]:
        if session_id in cache:
            return cache[session_id]
        srow = await self.db.sessions.get(session_id)
        if srow is None:
            cache[session_id] = []
            return []
        rounds = await self.db.sessions.read_rounds_file(srow["source"], session_id)
        cache[session_id] = rounds
        return rounds

    # ──────── audit log ────────

    async def _log(
        self, search_id: str, query: str, where: str | None,
        top_k: int, response: SearchResponse,
    ) -> None:
        body = response.model_dump(mode="json")
        now = _utc_iso()
        await self.db.search_log.insert(
            search_id=search_id, query=query, where_dsl=where,
            top_k=top_k, created_at=now, response=body,
        )
        # File mirror — one jsonl per UTC date.
        date_str = now[:10]
        path = self.config.search_log_dir / f"{date_str}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "search_id": search_id, "query": query, "where_dsl": where,
            "top_k": top_k, "created_at": now, "response": body,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
