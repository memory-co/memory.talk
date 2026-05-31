"""RecallService — POST /v3/recall (hook), list, read.

0.9.0 rewrite — see ``docs/structure/v3/recall.md`` for the data model.

Architecture:

  recall.jsonl (canonical, per-session file)
       │  append-only, contains insight snapshots + source/location/top_k
       │
       ▼
  recall_event (SQLite derived index)
       │  card_id arrays only; rebuilds from file (impl deferred)
       │
       ▼  read-time queries
  dedup · list · read · derived recall_count (search/read display)

Write order is **file first, SQLite second**. SQLite write failure is
logged but does not abort the hook — file already has the truth, future
rebuild brings SQLite back in sync.

Hook caller MUST pass ``source`` (e.g. ``claude-code`` / ``codex``).
``location`` defaults to the adapter's ``DEFAULT_LOCATION``. Together
they parameterize ``BaseAdapter.mint_session_id`` so the canonical
session_id matches what sync will eventually write for the same
upstream conversation.
"""
from __future__ import annotations
import datetime as _dt
import logging

from memorytalk.adapters import get_adapter
from memorytalk.config import Config
from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore
from memorytalk.repository import SQLiteStore
from memorytalk.util.ids import new_event_id


# Pull more candidates than the user's top_k so the dedup pass has room
# to skip already-recalled ids and still fill the quota.
_RECALL_OVERSAMPLE = 5


_log = logging.getLogger(__name__)


class RecallServiceError(Exception):
    pass


def _utc_iso() -> str:
    # microsecond precision so events landing in the same second still
    # sort deterministically (recall_event ORDER BY ts assumes this).
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


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

    # ──────────── hook (write) ────────────

    async def recall(
        self,
        *,
        source: str,
        location: str | None,
        raw_session_id: str,
        prompt: str,
        top_k: int | None,
    ) -> dict:
        """Hook entrypoint. Computes canonical session_id from
        (source, location, raw_session_id), runs vector search,
        dedups against this session's prior recalls, writes
        ``recall.jsonl`` then ``recall_event``, returns the new cards
        + the cards skipped due to dedup."""
        if not prompt or not prompt.strip():
            raise RecallServiceError("prompt required")

        top_k = top_k or self.config.settings.recall.default_top_k
        if top_k < 1 or top_k > 50:
            raise RecallServiceError("top_k out of range (1..50)")

        # Mint canonical session_id via the right adapter. This is the
        # whole reason hook callers must supply ``source`` — without
        # it we'd be guessing (0.8.x bug: hardcoded claude-code).
        try:
            adapter = get_adapter(source, location)
        except ValueError as e:
            raise RecallServiceError(str(e)) from e
        canonical_sid = adapter.mint_session_id(raw_session_id)

        if self.vectors is None:
            return {
                "session_id": canonical_sid, "query": prompt,
                "recalled": [], "skipped_already_recalled": [],
            }

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

        # Dedup against this session's prior recalls (derived from
        # recall_event JSON via json_each).
        candidate_ids = [h["card_id"] for h in hits if h.get("card_id")]
        already = await self.db.recall.already_recalled(canonical_sid, candidate_ids)

        # Walk hits in order; collect top_k new + report ALL already-skipped.
        new_ids: list[str] = []
        skipped_ids: list[str] = []
        for h in hits:
            cid = h.get("card_id")
            if not cid:
                continue
            if cid in already:
                skipped_ids.append(cid)
                continue
            if len(new_ids) < top_k:
                new_ids.append(cid)
            # else: hit beyond top_k quota; silently drop (NOT in
            # skipped_already_recalled — that field is specifically
            # about dedup, not top_k cap).

        # Materialize insight snapshots for BOTH returned + skipped.
        # File records both for audit ("why didn't this round return
        # anything new? oh, all the candidates were already shown").
        returned = await self._materialize(new_ids)
        skipped = await self._materialize(skipped_ids)

        # Build the canonical event record.
        event = {
            "event_id": new_event_id(),
            "session_id": canonical_sid,
            "source": source,
            "location": adapter.location,
            "ts": _utc_iso(),
            "prompt": prompt,
            "top_k": top_k,
            "returned": returned,
            "skipped": skipped,
        }

        # ── write path: file first (canonical), SQLite second (derived).
        # Always write — even when ``returned`` is empty (every hook
        # call is one event, including "all candidates were skipped"
        # and "nothing matched"). ``recall read`` needs those events to
        # answer "why didn't this round give me anything new?".

        # File write goes through the storage abstraction so the
        # session dir gets mkdir'd alongside meta.json / rounds.jsonl.
        # If this raises, the hook caller will translate to an empty
        # hookSpecificOutput (contract: hook never exits non-zero).
        await self.db.sessions.append_recall_event(
            source, canonical_sid, event,
        )

        # SQLite is a derived index. Failure here is non-fatal —
        # file has the truth and a future rebuild restores SQLite.
        try:
            await self.db.recall.insert_event(
                event_id=event["event_id"],
                session_id=canonical_sid,
                prompt=prompt,
                ts=event["ts"],
                returned_card_ids=[c["card_id"] for c in returned],
                skipped_card_ids=[c["card_id"] for c in skipped],
            )
        except Exception as e:  # noqa: BLE001
            _log.warning(
                "recall_event SQLite insert failed for %s; "
                "file is canonical, rebuild will recover: %s",
                canonical_sid, e,
            )

        return {
            "session_id": canonical_sid, "query": prompt,
            "recalled": returned,
            "skipped_already_recalled": [c["card_id"] for c in skipped],
        }

    async def _materialize(self, card_ids: list[str]) -> list[dict]:
        """Look up each card_id and return ``[{card_id, insight}, ...]``.
        Drops ids whose cards are missing (LanceDB row exists but card
        row missing — rolled-back card, race window during rebuild)."""
        out: list[dict] = []
        for cid in card_ids:
            row = await self.db.cards.get(cid)
            if row is None:
                continue
            out.append({"card_id": cid, "insight": row["insight"]})
        return out

    # ──────────── list (read) ────────────

    async def list_sessions(self, *, limit: int = 20) -> dict:
        """For ``memory.talk recall list``."""
        if limit < 1 or limit > 200:
            raise RecallServiceError("limit out of range (1..200)")
        rows = await self.db.recall.list_sessions(limit=limit)
        return {"sessions": rows}

    # ──────────── read (read) ────────────

    async def read_session(
        self,
        canonical_session_id: str,
        *,
        limit: int = 50,
        reverse: bool = False,
    ) -> dict:
        """For ``memory.talk recall read <session_id>``.

        Returns the timeline of events for one session. ``returned`` and
        ``skipped`` are enriched with the CURRENT card insight (joined
        from cards table) — that's the recall's *current* view. The
        history snapshot lives in the file (``recall.jsonl``) and can
        be consulted separately for "what insight was shown at the
        time" forensic questions."""
        if limit < 1 or limit > 500:
            raise RecallServiceError("limit out of range (1..500)")
        events = await self.db.recall.get_session_events(
            canonical_session_id, limit=limit, reverse=reverse,
        )
        # Enrich card_id arrays with current insights.
        for ev in events:
            ev["returned"] = await self._materialize(ev.pop("returned_ids"))
            ev["skipped"] = await self._materialize(ev.pop("skipped_ids"))
        return {"session_id": canonical_session_id, "events": events}
