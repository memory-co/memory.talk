"""RecallService — POST /v3/recall.

Recall is "search, but cards-only + per-session dedup". Reuses the
LanceDB hybrid path (``LanceStore.search_cards``) — no DSL / no formula
/ no audit log. Each new returned card increments its ``recall_count``
stat and gets recorded in ``recall_log`` so the next call against the
same session skips it.

Session id normalization is the only point where this method needs to
know about platform raw ids vs prefixed ids — calls with either form
work; downstream uses the prefixed form.
"""
from __future__ import annotations
import datetime as _dt

from memorytalk.config import Config
from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore
from memorytalk.repository import SQLiteStore
from memorytalk.util.ids import prefix_session_id


# Pull more candidates than the user's top_k so the dedup pass has room
# to skip already-recalled ids and still fill the quota.
_RECALL_OVERSAMPLE = 5


class RecallServiceError(Exception):
    pass


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class RecallService:
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

    async def recall(
        self, session_id: str, prompt: str, top_k: int | None,
    ) -> dict:
        if not prompt or not prompt.strip():
            raise RecallServiceError("prompt required")

        top_k = top_k or self.config.settings.recall.default_top_k
        if top_k < 1 or top_k > 50:
            raise RecallServiceError("top_k out of range (1..50)")

        sid = prefix_session_id(session_id)

        if self.vectors is None:
            return {"session_id": sid, "query": prompt,
                    "recalled": [], "skipped_already_recalled": []}

        # Build query vector + ensure FTS index, same as search.
        qvec: list[float] | None = None
        if self.embedder is not None:
            try:
                qvec = await self.embedder.embed_one(prompt)
            except Exception:
                qvec = None
        try:
            await self.vectors.ensure_fts_index(self.vectors.CARDS)
        except Exception:
            pass

        oversample = max(top_k * _RECALL_OVERSAMPLE, top_k + 5)
        hits = await self.vectors.search_cards(
            query=prompt, vector=qvec, top_k=oversample,
        )

        # Dedup against this session's recall_log.
        candidate_ids = [h["card_id"] for h in hits if h.get("card_id")]
        already = await self.db.recall.already_recalled(sid, candidate_ids)

        # Walk hits in order; collect top_k new + report ALL already-skipped.
        new_ids: list[str] = []
        skipped: list[str] = []
        for h in hits:
            cid = h.get("card_id")
            if not cid:
                continue
            if cid in already:
                skipped.append(cid)
                continue
            if len(new_ids) < top_k:
                new_ids.append(cid)
            # else: still a valid hit, just past the quota — silently drop
            # (don't list under skipped_already_recalled — that field is
            # specifically about dedup, not top_k cap).

        # Materialize insight text for the new ids.
        recalled: list[dict] = []
        valid_new_ids: list[str] = []
        for cid in new_ids:
            card_row = await self.db.cards.get(cid)
            if card_row is None:
                continue  # LanceDB row exists but card row missing — skip
            recalled.append({"card_id": cid, "insight": card_row["insight"]})
            valid_new_ids.append(cid)

        # Side effects: record + bump recall_count.
        if valid_new_ids:
            now = _utc_iso()
            await self.db.recall.record(sid, valid_new_ids, now)
            for cid in valid_new_ids:
                await self.db.cards.bump_recall(cid, now)

        return {
            "session_id": sid, "query": prompt,
            "recalled": recalled,
            "skipped_already_recalled": skipped,
        }
