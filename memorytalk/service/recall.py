"""Recall service — hook-stage automatic memory injection.

Distinct from Search:
- bypasses ``search_log`` audit (recall has its own ``recall`` /
  ``recall_hit`` tables)
- only retrieves CARDS (sessions are too long to inline into prompts)
- atomic per-session round counter via UPSERT-RETURNING
- sliding-window dedup over the last K rounds (``settings.recall.dedup_window_rounds``)
- doesn't refresh TTL (auto-recall != intentional use)
"""
from __future__ import annotations

from memorytalk.config import Config
from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import RecallHit, RecallRequest, RecallResponse
from memorytalk.util.ids import prefix_session_id
from memorytalk.util.ttl import dt_to_iso, now_utc


class RecallError(ValueError):
    """400 — invalid input."""


class RecallService:
    def __init__(
        self, *,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore,
        embedder: Embedder,
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.embedder = embedder

    async def recall(self, payload: RecallRequest) -> RecallResponse:
        if not payload.session_id:
            raise RecallError("session_id required")
        if not payload.query or not payload.query.strip():
            raise RecallError("query required")

        cfg = self.config.settings.recall
        top_k = payload.top_k or cfg.default_top_k
        if top_k <= 0 or top_k > 100:
            raise RecallError("top_k out of range (1..100)")

        session_id = prefix_session_id(payload.session_id)

        now = now_utc()
        now_iso = dt_to_iso(now)

        # 1. atomic round counter — also touches recall.last_at / last_query
        round_count = await self.db.recall.bump_round(
            session_id, query=payload.query, now_iso=now_iso,
        )

        # 2. ensure FTS index exists (search service does this; recall must too
        #    because it bypasses SearchService).
        await self.vectors.ensure_fts_index("cards")

        # 3. fetch a buffered candidate set — dedup may eat some, so pull more.
        fetch_k = top_k * cfg.fetch_multiplier
        vector = await self.embedder.embed_one(payload.query)
        raw = await self.vectors.hybrid_search_cards(
            vector, payload.query, whitelist=None, top_k=fetch_k,
        )
        candidates: list[str] = [r.get("card_id") for r in raw if r.get("card_id")]

        # 4. dedup against the sliding window
        seen = await self.db.recall.seen_in_window(
            session_id, candidates,
            current_round=round_count, window=cfg.dedup_window_rounds,
        )

        # 5. take the first top_k that aren't in `seen`
        fresh: list[str] = []
        skipped: list[str] = []
        for cid in candidates:
            if cid in seen:
                if len(skipped) < top_k:
                    skipped.append(cid)
                continue
            if len(fresh) < top_k:
                fresh.append(cid)
            if len(fresh) >= top_k:
                break

        # 6. fetch summaries for the fresh cards — used both in the response
        #    and denormalized into recall_hit so review detail can replay
        #    "what Claude saw at the time".
        fresh_with_summary: list[tuple[str, str]] = []
        for cid in fresh:
            card = await self.db.cards.get(cid)
            if card is None:
                continue
            fresh_with_summary.append((cid, card["summary"]))

        # 7. record actually-injected hits with their summaries (skipped rows
        #    are not persisted — they are reproducible from recall_hit history).
        if fresh_with_summary:
            await self.db.recall.record_hits(
                session_id,
                round_count=round_count, query=payload.query, now_iso=now_iso,
                hits=[
                    (cid, rank, summary)
                    for rank, (cid, summary) in enumerate(fresh_with_summary, start=1)
                ],
            )

        # 8. assemble response from the same fetched summaries.
        hits = [
            RecallHit(card_id=cid, summary=summary)
            for cid, summary in fresh_with_summary
        ]

        return RecallResponse(
            session_id=session_id,
            round_count=round_count,
            query=payload.query,
            recalled=hits,
            skipped_already_recalled=skipped,
        )
