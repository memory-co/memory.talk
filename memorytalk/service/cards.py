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
a NEW competing Position (``forked_from`` records lineage). Reviews are
append-only too. credence is computed at read time, never stored (see
``credence``).

Positions/CardLinks have no global id — they are card-scoped subordinates
addressed ``card_id#p<n>`` / ``card_id#l<n>``. A review targets one of
those addresses; ``target_kind`` ('position'|'link') is derived from the
seq prefix.
"""
from __future__ import annotations

import datetime as _dt
import logging

from memorytalk.repository import SQLiteStore
from memorytalk.repository.card_links import _target_type
from memorytalk.repository.reviews import target_kind_of
from memorytalk.schemas.card_requests import (
    CreateCardRequest, CreateLinkRequest, CreatePositionRequest,
    CreateReviewRequest,
)
from memorytalk.searchbase import Doc, SearchBackend
from memorytalk.service.events import EventWriter
from memorytalk.service.searchbase_schema import V4_CARDS, V4_POSITIONS, cap_text
from memorytalk.util.ids import (
    CARD_PREFIX, FRAGMENT_SEP, IdKind, InvalidIdError, SESSION_PREFIX,
    SESSION_PREFIX_LEGACY, new_card_id, new_review_id, parse_fragment,
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
        if req.card_id and await self.db.cards.exists(card_id):
            raise CardConflict(f"card_id {card_id} already exists")

        now = _utc_iso()
        await self.db.cards.insert(card_id, req.issue, now)
        await self.db.cards.write_doc({
            "card_id": card_id, "issue": req.issue, "created_at": now,
        })
        await self._index(V4_CARDS, card_id, req.issue, {}, card_id)
        await self.events.card_event(
            card_id, "created", issue_preview=req.issue[:80],
        )
        return card_id

    # ────────── add position (claim) ──────────

    async def add_position(self, card_id: str, req: CreatePositionRequest) -> str:
        """Mint the next card-scoped ``p<n>``, persist it, mirror the file
        doc, and record one ``position_sessions`` row per ``--source`` (each
        position→session, ``position=p<n>``, via its ``indexes``). Returns
        the minted ``position`` ('p<n>')."""
        if not await self.db.cards.exists(card_id):
            raise CardNotFound(f"card {card_id} not found")
        if not req.claim or not req.claim.strip():
            raise CardServiceError("claim required")
        srcs = req.all_sources()
        for s in srcs:
            await self._require_session(s.session_id, s.indexes)
        if req.forked_from is not None:
            fp = req.forked_from
            if not (fp.startswith("p") and fp[1:].isdigit()):
                raise CardServiceError("invalid forked_from seq (expected 'p<n>')")
            if not await self.db.positions.exists(card_id, fp):
                raise CardServiceError(f"position {card_id}#{fp} not found")

        now = _utc_iso()
        position = await self.db.positions.insert(
            card_id, req.claim, now,
            scope=req.scope or "", forked_from=req.forked_from,
        )
        # file canonical = position + claim + created_at (scope/fork are
        # SQLite runtime state, not part of the write-once file core).
        await self.db.positions.write_doc(card_id, {
            "position": position, "card_id": card_id,
            "claim": req.claim, "created_at": now,
        })
        for s in srcs:
            await self.db.position_sessions.insert(
                card_id, position, s.session_id, s.indexes, now,
            )
        await self._index(
            V4_POSITIONS, f"{card_id}{FRAGMENT_SEP}{position}", req.claim,
            {"card_id": card_id}, card_id,
        )
        await self.events.card_event(
            card_id, "position_added", position=position,
            forked_from=req.forked_from,
        )
        return position

    # ────────── review (argument ±1/0) on a Position OR a CardLink ──────────

    async def review(self, target: str, req: CreateReviewRequest) -> dict:
        """Review an addressed subordinate ``card_id#p<n>`` / ``card_id#l<n>``.
        Inserts the review and bumps the matching store's argument tallies."""
        try:
            base_id, kind, seq = parse_fragment(target)
        except InvalidIdError as e:
            raise CardServiceError(str(e)) from e
        if FRAGMENT_SEP not in target or kind not in (IdKind.POSITION, IdKind.LINK):
            raise CardServiceError(
                "review target must be card_id#p<n> or card_id#l<n>",
            )
        card_id = base_id
        if req.argument not in (-1, 0, 1):
            raise CardServiceError("argument must be one of 1, 0, -1")

        if kind is IdKind.POSITION:
            if await self.db.positions.get(card_id, seq) is None:
                raise CardNotFound(f"position {target} not found")
        else:
            if await self.db.card_links.get(card_id, seq) is None:
                raise CardNotFound(f"link {target} not found")
        await self._require_session(req.session_id, req.indexes)

        review_id = req.review_id or new_review_id()
        if await self.db.reviews.exists(review_id):
            raise CardConflict(f"review_id {review_id} already exists")

        target_kind = target_kind_of(seq)
        now = _utc_iso()
        await self.db.reviews.insert(
            review_id, card_id, seq, target_kind, req.session_id, req.indexes,
            req.argument, req.comment, now,
        )
        if kind is IdKind.POSITION:
            await self.db.positions.bump_argument(card_id, seq, req.argument)
        else:
            await self.db.card_links.bump_argument(card_id, seq, req.argument)
        await self.events.card_event(
            card_id, "reviewed", review_id=review_id, target=seq,
            target_kind=target_kind, argument=req.argument,
            session_id=req.session_id, indexes=req.indexes,
        )
        return {
            "status": "ok", "review_id": review_id,
            "target": f"{card_id}{FRAGMENT_SEP}{seq}", "target_kind": target_kind,
            "card_id": card_id, "session_id": req.session_id,
            "argument": req.argument,
        }

    # ────────── link (governed IBIS edge) ──────────

    async def link(self, card_id: str, req: CreateLinkRequest) -> dict:
        """Draw a governed IBIS edge. ``claim`` (why this edge) is required;
        the edge is addressed ``card_id#l<n>`` and is itself reviewable.
        Idempotent on (card_id, type, target_id). Returns the edge's
        ``link`` seq + derived ``target_type``."""
        if not await self.db.cards.exists(card_id):
            raise CardNotFound(f"card {card_id} not found")
        if req.type not in _LINK_TYPES:
            raise CardServiceError(f"unknown link type: {req.type}")
        if not req.claim or not req.claim.strip():
            raise CardServiceError("claim required")
        for s in req.source:
            await self._require_session(s.session_id, s.indexes)
        target = req.target_id
        target_type = _target_type(target)
        if target_type == "position":
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
        # CardLinkStore.insert mints the seq AND bumps cards.link_count
        # itself on a fresh row (idempotent on dup → no extra bump). The
        # service only mirrors the file doc + emits the event for new edges.
        link = await self.db.card_links.insert(subject, req.type, tgt, req.claim, now)
        # One link_sessions row per --source (link→session via indexes),
        # mirroring how a Position's --source lands position_sessions.
        # INSERT OR IGNORE → idempotent, so re-citing a dup edge is safe.
        for s in req.source:
            await self.db.link_sessions.insert(
                subject, link, s.session_id, s.indexes, now,
            )
        if not already:
            await self.db.card_links.write_doc(subject, {
                "link": link, "card_id": subject, "type": req.type,
                "target_id": tgt, "claim": req.claim, "created_at": now,
            })
            await self.events.card_event(
                subject, "card_linked", link=link, type=req.type, target_id=tgt,
            )
        return {
            "status": "ok", "card_id": subject, "link": link, "type": req.type,
            "target_id": tgt, "target_type": _target_type(tgt), "claim": req.claim,
        }

    # ────────── delete card (hard-delete escape hatch) ──────────

    async def delete_card(self, card_id: str, *, dry_run: bool) -> dict:
        """Hard-delete a card and ALL associated data (escape hatch — the
        governed model normally prefers ``review -1`` + counter-edge, NOT
        delete). Computes the cascade plan first; on a real run executes it
        atomically (files → rows → vectors). Returns the affected counts.

        Cascade scope:
          • OUTgoing + own state: the card dir (card.json + positions/ +
            links/), and SQLite ``cards`` / ``positions`` / ``reviews`` /
            ``card_links``(subject) / ``card_sessions`` / ``position_sessions``
            / ``link_sessions``; vector ``cards``[card_id] + ``positions``
            docs of this card.
          • INcoming edges: each ``card_links`` row from ANOTHER card whose
            ``target_id`` is this card (or ``card_id#…``) — drop the row,
            the source card's link file, and that link's ``link_sessions``
            (so the other card no longer dangles). The source card's other
            data is left intact.
        """
        if not await self.db.cards.exists(card_id):
            raise CardNotFound(f"card {card_id} not found")

        # ── gather the plan (read-only) ──
        positions = await self.db.positions.list_for_card(card_id)
        reviews = await self.db.reviews.list_for_card(card_id)
        out_links = await self.db.card_links.list_out(card_id)
        in_links = await self.db.card_links.list_incoming(card_id)
        card_sessions = await self.db.card_sessions.list_for_card(card_id)
        # position_sessions / link_sessions provenance totals (own state).
        own_provenance = len(card_sessions)
        for p in positions:
            own_provenance += len(
                await self.db.position_sessions.list_for_position(card_id, p["position"]))
        for l in out_links:
            own_provenance += len(
                await self.db.link_sessions.list_for_link(card_id, l["link"]))
        in_provenance = 0
        for l in in_links:
            in_provenance += len(
                await self.db.link_sessions.list_for_link(l["card_id"], l["link"]))

        counts = {
            "positions": len(positions),
            "reviews": len(reviews),
            "links_out": len(out_links),
            "links_in": len(in_links),
            "provenance": own_provenance + in_provenance,
            "vectors": 1 + len(positions),
        }
        issue = (await self.db.cards.get(card_id) or {}).get("issue", "")

        if dry_run:
            return {"card_id": card_id, "issue": issue, "counts": counts}

        # ── execute the cascade: incoming edges first (other cards), then
        #    own files (the whole card dir), then own rows, then vectors. ──
        for l in in_links:
            await self.db.link_sessions.delete_for_link(l["card_id"], l["link"])
            await self.db.card_links.delete_link(l["card_id"], l["link"])

        # Own card dir (card.json + positions/ + links/) + cards row.
        await self.db.cards.delete(card_id)
        # Own subordinate rows.
        await self.db.positions.delete_for_card(card_id)
        await self.db.reviews.delete_for_card(card_id)
        await self.db.card_links.delete_outgoing(card_id)
        await self.db.card_sessions.delete_for_card(card_id)
        await self.db.position_sessions.delete_for_card(card_id)
        await self.db.link_sessions.delete_for_card(card_id)
        # Vectors (best-effort): the issue doc + every position claim doc.
        if self.search is not None:
            try:
                await self.search.delete(V4_CARDS, [card_id])
                await self.search.delete_where(V4_POSITIONS, {"card_id": card_id})
            except Exception as e:   # best-effort: a rebuild reconciles later
                _log.warning("vector delete failed for %s: %s", card_id, e)

        return {"card_id": card_id, "deleted": counts}

    # ────────── internal: best-effort vector upsert ──────────

    async def _index(self, collection: str, doc_id: str, text: str, fields: dict, card_id: str) -> None:
        if self.search is None:
            return
        try:
            await self.search.upsert(collection, [Doc(id=doc_id, text=cap_text(text), fields=fields)])
        except Exception as e:   # best-effort: a rebuild can fill it in later
            await self.events.card_event(card_id, "vector_index_failed", error=str(e), doc_id=doc_id)
