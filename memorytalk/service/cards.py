"""CardService — the v4 write path (governed question graph).

One Card = one Issue (the question); several Positions (candidate answers)
compete by computed credence; ``card_links`` are IBIS edges; ``reviews``
are stances (argument ±1/0) on a Position; ``card_sessions`` trace
provenance.

Persistence per write (mirrors InsightService ordering):
  1. SQLite row(s) + redundant counter bumps
  2. file-canonical mirror (card.json / positions/<pid>.json)
  3. best-effort LanceDB upsert (cards=issue, positions=claim)
  4. lifecycle event(s) (cards/<bucket>/<card_id>/events.jsonl)

Append-only: a Position is never mutated or deleted — a changed answer is
a NEW competing Position (``forked_from_position_id`` records lineage).
Reviews are append-only too. credence is computed at read time, never
stored (see ``v4_credence``).
"""
from __future__ import annotations

import datetime as _dt
import logging

from memorytalk.repository import SQLiteStore
from memorytalk.schemas.v4.requests import (
    CreateCardRequest, CreateLinkRequest, CreatePositionRequest,
    CreateReviewRequest,
)
from memorytalk.searchbase import Doc, SearchBackend
from memorytalk.service.events import EventWriter
from memorytalk.service.searchbase_schema import V4_CARDS, V4_POSITIONS, cap_text
from memorytalk.util.ids import (
    CARD_PREFIX, POSITION_PREFIX, SESSION_PREFIX, SESSION_PREFIX_LEGACY,
    new_card_id, new_position_id, new_review_id,
)
from memorytalk.util.indexes import IndexesParseError, parse_indexes

_log = logging.getLogger(__name__)


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

_LINK_TYPES = {"specializes", "suggested_by", "questions", "replaces", "related"}
# Only ``suggested_by`` may point at a Position; the rest are card↔card.
_POSITION_TARGET_OK = {"suggested_by"}


class CardServiceError(Exception):
    """4xx-equivalent: validation failed, request rejected."""


class CardConflict(CardServiceError):
    """409-equivalent: the supplied id already exists."""


class CardNotFound(CardServiceError):
    """404-equivalent: a referenced card/position doesn't exist."""


def _is_session_id(sid: str) -> bool:
    return sid.startswith(SESSION_PREFIX) or sid.startswith(SESSION_PREFIX_LEGACY)


class CardService:
    def __init__(self, db: SQLiteStore, search: SearchBackend | None, events: EventWriter):
        self.db = db
        self.search = search
        self.events = events

    # ────────── helpers ──────────

    async def _require_session(self, session_id: str, indexes: str) -> None:
        """Validate a (session_id, indexes) provenance/evidence ref."""
        if not _is_session_id(session_id):
            raise CardServiceError("invalid session_id prefix")
        if await self.db.sessions.get(session_id) is None:
            raise CardServiceError(f"session {session_id} not found")
        try:
            parse_indexes(indexes)
        except IndexesParseError as e:
            raise CardServiceError(str(e)) from e

    # ────────── create card (issue) ──────────

    async def create_card(self, req: CreateCardRequest) -> str:
        if not req.issue or not req.issue.strip():
            raise CardServiceError("issue required")
        card_id = req.card_id or new_card_id()
        if not card_id.startswith(CARD_PREFIX):
            raise CardServiceError("invalid card_id prefix")
        if req.card_id and await self.db.v4cards.exists(card_id):
            raise CardConflict(f"card_id {card_id} already exists")

        now = _utc_iso()
        await self.db.v4cards.insert(card_id, req.issue, now)
        await self.db.v4cards.write_doc({
            "card_id": card_id, "issue": req.issue, "created_at": now,
        })
        await self._index(V4_CARDS, card_id, req.issue, {}, card_id)
        await self.events.card_event(
            card_id, "created", issue_preview=req.issue[:80],
        )
        return card_id

    # ────────── add position (claim) ──────────

    async def add_position(self, card_id: str, req: CreatePositionRequest) -> str:
        if not await self.db.v4cards.exists(card_id):
            raise CardNotFound(f"card {card_id} not found")
        if not req.claim or not req.claim.strip():
            raise CardServiceError("claim required")
        if req.source is not None:
            await self._require_session(req.source.session_id, req.source.indexes)
        if req.forked_from_position_id is not None:
            fp = req.forked_from_position_id
            if not fp.startswith(POSITION_PREFIX):
                raise CardServiceError("invalid forked_from_position_id prefix")
            if not await self.db.positions.exists(fp):
                raise CardServiceError(f"position {fp} not found")

        position_id = req.position_id or new_position_id()
        if not position_id.startswith(POSITION_PREFIX):
            raise CardServiceError("invalid position_id prefix")
        if req.position_id and await self.db.positions.exists(position_id):
            raise CardConflict(f"position_id {position_id} already exists")

        now = _utc_iso()
        await self.db.positions.insert(
            position_id, card_id, req.claim, now,
            scope=req.scope or "", forked_from_position_id=req.forked_from_position_id,
        )
        # file canonical = claim + created_at only (scope/fork are SQLite runtime state)
        await self.db.positions.write_doc(card_id, {
            "position_id": position_id, "card_id": card_id,
            "claim": req.claim, "created_at": now,
        })
        await self.db.v4cards.bump_position_count(card_id)
        if req.source is not None:
            await self.db.card_sessions.insert(
                card_id, req.source.session_id, position_id, req.source.indexes, now,
            )
        await self._index(
            V4_POSITIONS, position_id, req.claim, {"card_id": card_id}, card_id,
        )
        await self.events.card_event(
            card_id, "position_added", position_id=position_id,
            forked_from_position_id=req.forked_from_position_id,
        )
        return position_id

    # ────────── review (argument ±1/0) ──────────

    async def review(self, position_id: str, req: CreateReviewRequest) -> dict:
        if not position_id.startswith(POSITION_PREFIX):
            raise CardServiceError("invalid position_id prefix")
        pos = await self.db.positions.get(position_id)
        if pos is None:
            raise CardNotFound(f"position {position_id} not found")
        if req.argument not in (-1, 0, 1):
            raise CardServiceError("argument must be one of 1, 0, -1")
        await self._require_session(req.session_id, req.indexes)

        review_id = req.review_id or new_review_id()
        if await self.db.v4reviews.exists(review_id):
            raise CardConflict(f"review_id {review_id} already exists")

        card_id = pos["card_id"]
        now = _utc_iso()
        await self.db.v4reviews.insert(
            review_id, position_id, card_id, req.session_id, req.indexes,
            req.argument, req.comment, now,
        )
        await self.db.positions.bump_argument(position_id, req.argument)
        await self.events.card_event(
            card_id, "reviewed", review_id=review_id, position_id=position_id,
            argument=req.argument, session_id=req.session_id, indexes=req.indexes,
        )
        return {
            "status": "ok", "review_id": review_id, "position_id": position_id,
            "card_id": card_id, "session_id": req.session_id, "argument": req.argument,
        }

    # ────────── link (IBIS edge) ──────────

    async def link(self, card_id: str, req: CreateLinkRequest) -> dict:
        if not await self.db.v4cards.exists(card_id):
            raise CardNotFound(f"card {card_id} not found")
        if req.type not in _LINK_TYPES:
            raise CardServiceError(f"unknown link type: {req.type}")
        target = req.target_id
        if target.startswith(POSITION_PREFIX):
            if req.type not in _POSITION_TARGET_OK:
                raise CardServiceError(
                    f"link type {req.type!r} cannot target a position",
                )
        elif not target.startswith(CARD_PREFIX):
            raise CardServiceError("invalid target_id prefix")

        # ``related`` is symmetric — canonicalize endpoint order so A→B and
        # B→A dedupe to one row (smaller id is the stored subject).
        subject, tgt = card_id, target
        if req.type == "related" and tgt < subject:
            subject, tgt = tgt, subject

        existing = await self.db.card_links.list_out(subject)
        already = any(e["type"] == req.type and e["target_id"] == tgt for e in existing)
        now = _utc_iso()
        await self.db.card_links.insert(subject, req.type, tgt, now)
        if not already:
            await self.db.v4cards.bump_link_count(subject)
            await self.events.card_event(
                subject, "card_linked", type=req.type, target_id=tgt,
            )
        target_type = "position" if tgt.startswith(POSITION_PREFIX) else "card"
        return {
            "status": "ok", "card_id": subject, "type": req.type,
            "target_id": tgt, "target_type": target_type,
        }

    # ────────── add session (provenance) ──────────

    async def add_session(
        self, card_id: str, session_id: str, position_id: str = "",
        indexes: str = "[]",
    ) -> dict:
        if not await self.db.v4cards.exists(card_id):
            raise CardNotFound(f"card {card_id} not found")
        if not _is_session_id(session_id):
            raise CardServiceError("invalid session_id prefix")
        if position_id and not position_id.startswith(POSITION_PREFIX):
            raise CardServiceError("invalid position_id prefix")
        now = _utc_iso()
        await self.db.card_sessions.insert(card_id, session_id, position_id, indexes, now)
        await self.events.card_event(
            card_id, "session_cited", session_id=session_id, position_id=position_id,
        )
        return {
            "status": "ok", "card_id": card_id, "session_id": session_id,
            "position_id": position_id,
        }

    # ────────── internal: best-effort vector upsert ──────────

    async def _index(self, collection: str, doc_id: str, text: str, fields: dict, card_id: str) -> None:
        if self.search is None:
            return
        try:
            await self.search.upsert(collection, [Doc(id=doc_id, text=cap_text(text), fields=fields)])
        except Exception as e:   # best-effort: a rebuild can fill it in later
            await self.events.card_event(card_id, "vector_index_failed", error=str(e), doc_id=doc_id)
