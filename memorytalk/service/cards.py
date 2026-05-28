"""CardService — POST /v3/cards.

Validates the create request, expands ``rounds[].indexes`` against the
source sessions' jsonl, persists across SQLite / files / LanceDB, and
fires the lifecycle events that other objects' audit trails need.

Persistence order (consistent with IngestService):

  1. SQLite `cards` + `card_stats` + `card_source_cards` (atomic-ish)
  2. File mirror: ``cards/<bucket>/<card_id>/card.json``
  3. LanceDB ``cards`` row (FTS + vector for search)

Events:

- ``cards/<bucket>/<card_id>/events.jsonl``        : ``created``
- referenced session's ``events.jsonl``            : ``card_extracted``
- each source_card's ``events.jsonl``              : ``card_linked``

Append-only & DAG invariants:

- ``rounds`` is expanded once at create time; the expanded list is
  stored on the card row and never re-resolved (session changes don't
  ripple into existing cards).
- ``source_cards`` requires referenced cards to **already exist** —
  this is the physical-time check that makes lineage a DAG with no
  runtime cycle detection.
"""
from __future__ import annotations
import datetime as _dt

from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import CreateCardRequest
from memorytalk.service.events import EventWriter
from memorytalk.util.ids import (
    CARD_PREFIX, SESSION_PREFIX, SESSION_PREFIX_LEGACY, new_card_id,
)
from memorytalk.util.indexes import IndexesParseError, parse_indexes
from memorytalk.util.tags import TagValidationError, validate_tag_dict


_ALLOWED_RELATIONS = {"derives_from", "supersedes"}


class CardServiceError(Exception):
    """4xx-equivalent: validation failed, request rejected."""


class CardConflict(CardServiceError):
    """409-equivalent: the supplied card_id already exists."""


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_thinking(content: list[dict]) -> str | None:
    """Pull the first ``thinking`` block's content out of a round, if any."""
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "thinking":
            t = b.get("thinking") or b.get("text")
            if t:
                return str(t)
    return None


class CardService:
    def __init__(
        self,
        db: SQLiteStore,
        vectors: LanceStore | None,
        embedder: Embedder | None,
        events: EventWriter,
    ):
        self.db = db
        self.vectors = vectors
        self.embedder = embedder
        self.events = events

    async def create(self, req: CreateCardRequest) -> str:
        """Validate + persist; return the card_id (auto-gen'd or supplied)."""
        if not req.insight or not req.insight.strip():
            raise CardServiceError("insight required")

        card_id = req.card_id or new_card_id()
        if not card_id.startswith(CARD_PREFIX):
            raise CardServiceError("invalid card_id prefix")
        if req.card_id and await self.db.cards.exists(card_id):
            raise CardConflict(f"card_id {card_id} already exists")

        # ── tags validation (pre-flight; reject whole create) ────────────
        # Validate before any DB write so a bad tag doesn't leave a
        # partially-created card behind. Same constraints PATCH uses.
        tags = dict(req.tags or {})
        if tags:
            try:
                validate_tag_dict(tags)
            except TagValidationError as e:
                raise CardServiceError(str(e)) from e

        # ── expand rounds ─────────────────────────────────────────────────
        expanded_rounds, referenced_sessions = await self._expand_rounds(req.rounds)

        # ── validate source_cards ────────────────────────────────────────
        for sc in req.source_cards:
            if not sc.card_id.startswith(CARD_PREFIX):
                raise CardServiceError("invalid source card_id prefix")
            if sc.relation not in _ALLOWED_RELATIONS:
                raise CardServiceError(f"unknown relation: {sc.relation}")
            if not await self.db.cards.exists(sc.card_id):
                raise CardServiceError(f"source card {sc.card_id} not found")

        now = _utc_iso()

        # ── 1. SQL ───────────────────────────────────────────────────────
        await self.db.cards.insert(card_id, req.insight, expanded_rounds, now, tags=tags)
        await self.db.cards.init_stats(card_id, now)
        if req.source_cards:
            await self.db.cards.insert_source_cards(card_id, [
                {"card_id": sc.card_id, "relation": sc.relation}
                for sc in req.source_cards
            ])

        # ── 2. File mirror ───────────────────────────────────────────────
        # card.json is the immutable-payload mirror — tags live in
        # their own ``tags.json`` sidecar so a later ``card tag`` PATCH
        # never has to touch card.json.
        await self.db.cards.write_doc({
            "card_id": card_id,
            "insight": req.insight,
            "rounds": expanded_rounds,
            "source_cards": [
                {"card_id": sc.card_id, "relation": sc.relation}
                for sc in req.source_cards
            ],
            "created_at": now,
        })
        if tags:
            await self.db.cards.write_tags_file(card_id, tags)

        # ── 3. LanceDB ───────────────────────────────────────────────────
        # Best-effort — like the sessions path, vector failure shouldn't
        # block card creation; a rebuild can fill it in later.
        if self.vectors is not None and self.embedder is not None:
            try:
                vec = await self.embedder.embed_one(req.insight)
                await self.vectors.add_card(card_id, req.insight, vec)
            except Exception as e:
                await self.events.card_event(
                    card_id, "vector_index_failed", error=str(e),
                )

        # ── 4. Events ────────────────────────────────────────────────────
        await self.events.card_event(
            card_id, "created",
            insight_preview=req.insight[:80],
            round_count=len(expanded_rounds),
            source_count=len(req.source_cards),
        )
        for sid, source in referenced_sessions:
            await self.events.session_event(source, sid, "card_extracted",
                                            card_id=card_id)
        for sc in req.source_cards:
            await self.events.card_event(
                sc.card_id, "card_linked",
                from_card=card_id, relation=sc.relation,
            )

        return card_id

    # ──────── helpers ────────

    async def _expand_rounds(self, refs) -> tuple[list[dict], list[tuple[str, str]]]:
        """Expand ``[{session_id, indexes}, ...]`` into stored CardRounds.

        Reads each referenced session's full rounds.jsonl once (cached per
        ``session_id`` within this call), parses the ``indexes`` string,
        and assembles one dict per matched round. Raises ``CardServiceError``
        if a session is missing or an index is out of range.

        Returns ``(expanded_rounds, [(session_id, source), ...])`` —
        the second list is used to fire ``card_extracted`` events.
        """
        cache: dict[str, list[dict]] = {}
        sources: dict[str, str] = {}  # session_id → source
        out: list[dict] = []
        for ref in refs:
            if not ref.session_id.startswith((SESSION_PREFIX, SESSION_PREFIX_LEGACY)):
                raise CardServiceError("invalid session_id prefix")
            session_row = await self.db.sessions.get(ref.session_id)
            if session_row is None:
                raise CardServiceError(f"session {ref.session_id} not found")
            sources[ref.session_id] = session_row["source"]

            try:
                want = parse_indexes(ref.indexes)
            except IndexesParseError as e:
                raise CardServiceError(str(e)) from e

            if ref.session_id not in cache:
                cache[ref.session_id] = await self.db.sessions.read_rounds_file(
                    session_row["source"], ref.session_id,
                )
            rounds_by_idx = {r["idx"]: r for r in cache[ref.session_id]}

            for idx in want:
                round_dict = rounds_by_idx.get(idx)
                if round_dict is None:
                    raise CardServiceError(
                        f"index {idx} out of range for session {ref.session_id}"
                    )
                out.append({
                    "role": round_dict.get("role") or "",
                    "text": round_dict.get("text") or "",
                    "thinking": _extract_thinking(round_dict.get("content") or []),
                    "session_id": ref.session_id,
                    "index": idx,
                })
        return out, list(sources.items())
