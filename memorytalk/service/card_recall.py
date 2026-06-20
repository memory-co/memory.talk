"""V4RecallService — unconscious recall at the hook boundary.

Embed the prompt, collide on issue AND claim, group by card, and for each
card surface its **current answer** (highest-credence Position; tie →
most-recent review) plus the runner-up ``alternatives`` and the answer's
``scope`` (a soft hint injected for the LLM to judge context — never a
gate). Cards are ranked by retrieval relevance, deduped against this
session's prior recalls. No Position field is ever written back; there is
no recall_count in v4.
"""
from __future__ import annotations

import datetime as _dt
import logging

from memorytalk.repository import SQLiteStore
from memorytalk.searchbase import SearchBackend
from memorytalk.service.cards import CardServiceError
from memorytalk.service.credence import sort_key, with_credence
from memorytalk.service.card_retrieval import retrieve
from memorytalk.util.ids import (
    SESSION_PREFIX, SESSION_PREFIX_LEGACY, new_event_id,
)

_log = logging.getLogger(__name__)
_DEFAULT_TOP_K = 5


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class V4RecallService:
    def __init__(self, db: SQLiteStore, search: SearchBackend | None):
        self.db = db
        self.search = search

    async def _answer_and_alts(self, card_id: str) -> tuple[dict | None, list[dict]]:
        rows = await self.db.positions.list_for_card(card_id)
        injected = []
        for r in rows:
            reviews = await self.db.reviews.list_for_target(card_id, r["position"])
            inj = with_credence(r, reviews[0]["created_at"] if reviews else None)
            inj["id"] = f"{card_id}#{r['position']}"
            injected.append(inj)
        injected.sort(key=sort_key, reverse=True)
        if not injected:
            return None, []
        return injected[0], injected[1:]

    async def recall(
        self, session_id: str, prompt: str, *, top_k: int = _DEFAULT_TOP_K,
    ) -> dict:
        if not (session_id.startswith(SESSION_PREFIX)
                or session_id.startswith(SESSION_PREFIX_LEGACY)):
            raise CardServiceError("invalid session_id prefix")
        if not prompt or not prompt.strip():
            raise CardServiceError("prompt required")
        if self.search is None:
            return {"session_id": session_id, "prompt": prompt, "cards": []}

        ranked = await retrieve(self.search, prompt, top_k)
        candidate_ids = [cid for cid, _ in ranked]
        already = await self.db.recall.already_recalled(session_id, candidate_ids)

        cards: list[dict] = []
        returned_ids: list[str] = []
        skipped_ids: list[str] = []
        for cid, meta in ranked:
            if cid in already:
                skipped_ids.append(cid)
                continue
            if len(cards) >= top_k:
                continue
            card = await self.db.cards.get(cid)
            if card is None:
                continue
            answer, alternatives = await self._answer_and_alts(cid)
            cards.append({
                "card_id": cid, "issue": card["issue"],
                "relevance": meta["relevance"],
                "answer": answer, "alternatives": alternatives,
            })
            returned_ids.append(cid)

        await self._record(session_id, prompt, returned_ids, skipped_ids)
        return {"session_id": session_id, "prompt": prompt, "cards": cards}

    async def _record(self, session_id: str, prompt: str,
                      returned_ids: list[str], skipped_ids: list[str]) -> None:
        """Append the canonical recall.jsonl line (file first) + the derived
        recall_event row (best-effort), so the next recall in this session
        dedups against these ids."""
        sess = await self.db.sessions.get(session_id)
        source = (sess or {}).get("source", "claude-code")
        event = {
            "event_id": new_event_id(), "session_id": session_id,
            "ts": _utc_iso(), "prompt": prompt,
            "returned": returned_ids, "skipped": skipped_ids,
        }
        try:
            await self.db.sessions.append_recall_event(source, session_id, event)
        except Exception as e:   # noqa: BLE001 — file write best-effort
            _log.warning("v4 recall.jsonl write failed for %s: %s", session_id, e)
        try:
            await self.db.recall.insert_event(
                event_id=event["event_id"], session_id=session_id, prompt=prompt,
                ts=event["ts"], returned_card_ids=returned_ids,
                skipped_card_ids=skipped_ids,
            )
        except Exception as e:   # noqa: BLE001 — SQLite derived, rebuildable
            _log.warning("v4 recall_event insert failed for %s: %s", session_id, e)
