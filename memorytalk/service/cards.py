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
import logging

from memorytalk.searchbase import Doc, SearchBackend
from memorytalk.service.searchbase_schema import INSIGHTS, cap_text
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import CreateCardRequest
from memorytalk.service.events import EventWriter
from memorytalk.util.ids import (
    CARD_PREFIX, SESSION_PREFIX, SESSION_PREFIX_LEGACY, new_card_id,
)
from memorytalk.util.indexes import IndexesParseError, parse_indexes
from memorytalk.util.tags import TagValidationError, validate_tag_dict


_ALLOWED_RELATIONS = {"derives_from", "supersedes"}

_log = logging.getLogger(__name__)


class CardServiceError(Exception):
    """4xx-equivalent: validation failed, request rejected."""


class CardConflict(CardServiceError):
    """409-equivalent: the supplied card_id already exists."""


class CardNotFound(CardServiceError):
    """404-equivalent: card_id doesn't exist."""


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
        search: "SearchBackend | None",
        events: EventWriter,
    ):
        self.db = db
        self.search = search
        self.events = events

    async def create(self, req: CreateCardRequest) -> str:
        """Validate + persist; return the card_id (auto-gen'd or supplied)."""
        if not req.insight or not req.insight.strip():
            raise CardServiceError("insight required")

        card_id = req.card_id or new_card_id()
        if not card_id.startswith(CARD_PREFIX):
            raise CardServiceError("invalid card_id prefix")
        if req.card_id and await self.db.insights.exists(card_id):
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
            if not await self.db.insights.exists(sc.card_id):
                raise CardServiceError(f"source card {sc.card_id} not found")

        now = _utc_iso()

        # ── 1. SQL ───────────────────────────────────────────────────────
        await self.db.insights.insert(card_id, req.insight, expanded_rounds, now,
                                   tags=tags, explore_id=req.explore_id)
        await self.db.insights.init_stats(card_id, now)
        if req.source_cards:
            await self.db.insights.insert_source_cards(card_id, [
                {"card_id": sc.card_id, "relation": sc.relation}
                for sc in req.source_cards
            ])

        # ── 2. File mirror ───────────────────────────────────────────────
        # card.json is the immutable-payload mirror — tags live in
        # their own ``tags.json`` sidecar so a later ``card tag`` PATCH
        # never has to touch card.json.
        await self.db.insights.write_doc({
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
            await self.db.insights.write_tags_file(card_id, tags)

        # ── 3. Vector index (searchbase) ─────────────────────────────────
        # Best-effort — like the sessions path, vector failure shouldn't
        # block card creation; a rebuild can fill it in later.
        if self.search is not None:
            try:
                await self.search.upsert(INSIGHTS, [
                    Doc(id=card_id, text=cap_text(req.insight), fields={}),
                ])
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

    # ──────── delete ────────

    async def delete(self, card_id: str) -> dict:
        """Remove a card from SQLite + vector + files. Idempotent in the
        sense that re-calling on an already-deleted id raises CardNotFound
        (not a silent no-op — callers should not call us twice).

        Order matters:

          1. Read inbound refs count for response.
          2. Delete SQLite card rows (cards + card_stats + outbound
             source_cards, atomic).
          3. Delete LanceDB vector (best-effort — orphan rows are
             filtered out at search time by ``card_row is None`` checks).
          4. Delete filesystem dir (best-effort — orphan dirs are
             cosmetic, no read path scans them).

        Steps 3 + 4 are best-effort: by the time we get there SQLite has
        already committed the deletion, and reverting it would leave us
        with a card the user thinks is gone but vector/files still show
        up in odd places. Failures get logged; the response still says
        "deleted" because from the user's POV it IS deleted. Cleanup
        scripts handle the orphans later.
        """
        row = await self.db.insights.get(card_id)
        if row is None:
            raise CardNotFound(f"card {card_id} not found")

        inbound = await self.db.insights.count_inbound_refs(card_id)

        # 1. SQLite — atomic across cards / card_stats / outbound source_cards.
        await self.db.insights.delete(card_id)

        # 3. Vector — best-effort.
        if self.search is not None:
            try:
                await self.search.delete(INSIGHTS, [card_id])
            except Exception as e:  # noqa: BLE001
                _log.warning(
                    "vector delete failed for %s; card_row is None will "
                    "filter orphan at search time: %s", card_id, e,
                )

        # 4. Files — best-effort.
        try:
            await self.db.insights.delete_files(card_id)
        except Exception as e:  # noqa: BLE001
            _log.warning(
                "file delete failed for %s; orphan dir is cosmetic: %s",
                card_id, e,
            )

        return {
            "card_id": card_id,
            "inbound_refs_dangling": inbound,
        }

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
