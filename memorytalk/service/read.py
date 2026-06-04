"""ReadService — prefix-dispatched read of card or session.

The CLI / API layer parses the id prefix and calls one of:
- ``read_card(card_id)`` → full Card with stats, source_cards, reviews, rounds
- ``read_session(session_id)`` → full Session with rounds (read from jsonl)

Card reads have a side effect: ``card.stats.read_count`` is bumped by one
and a ``read_at`` event is appended to the card's events.jsonl. Session
reads are pure (sessions don't participate in forum dynamics).

v3 storage note: session rounds live in the jsonl file, not SQLite. We
read directly from disk here. The jsonl is append-only and rounds are
written in idx order, so simple parse-and-return preserves ordering.
"""
from __future__ import annotations
import datetime as _dt

from memorytalk.repository import SQLiteStore
from memorytalk.schemas import (
    Card, CardRound, CardStats, ContentBlock, Review, Round, Session, SourceCard,
)
# CardNotFound is owned by service.cards (the card service is the canonical
# place for card lifecycle errors); re-exported here for callers that
# historically imported it from service.read.
from memorytalk.service.cards import CardNotFound
from memorytalk.service.events import EventWriter


class ReadServiceError(Exception):
    """Base for read service errors."""


class SessionNotFound(ReadServiceError):
    pass


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class ReadService:
    def __init__(self, db: SQLiteStore, events: EventWriter):
        self.db = db
        self.events = events

    async def read_card(self, card_id: str) -> tuple[Card, str]:
        """Return (card, read_at). Bumps read_count + emits a `read` event."""
        row = await self.db.cards.get(card_id)
        if row is None:
            raise CardNotFound(f"card {card_id} not found")

        now = _utc_iso()
        await self.db.cards.bump_read(card_id, now)
        await self.events.card_event(card_id, "read", read_at=now)

        stats_dict = await self.db.cards.get_stats(card_id)
        # Merge in derived recall_count (single source of truth lives in
        # recall_event; card_stats no longer carries the column).
        counts = await self.db.recall.recall_counts([card_id])
        stats_dict["recall_count"] = counts.get(card_id, 0)
        source_cards = await self.db.cards.list_source_cards(card_id)
        reviews_rows = await self.db.reviews.list_for_card(card_id)

        card = Card(
            card_id=row["card_id"],
            insight=row["insight"],
            source_cards=[SourceCard(**sc) for sc in source_cards],
            rounds=[CardRound(**r) for r in row["rounds"]],
            reviews=[Review(**r) for r in reviews_rows],
            stats=CardStats(**stats_dict),
            created_at=row["created_at"],
        )
        return card, now

    async def read_session(self, session_id: str) -> tuple[Session, str]:
        """Return (session, read_at). Sessions are pure reads — no stats touched."""
        row = await self.db.sessions.get(session_id)
        if row is None:
            raise SessionNotFound(f"session {session_id} not found")

        # Rounds live in the jsonl file. The file is append-only, so the
        # natural read order matches idx order. We re-emit the idx field
        # for the response (schema requires it).
        rounds_jsonl = await self.db.sessions.read_rounds_file(row["source"], session_id)
        rounds = [
            Round(
                index=r["idx"],
                round_id=r["round_id"],
                parent_id=r.get("parent_id"),
                timestamp=r.get("timestamp"),
                speaker=r.get("speaker"),
                role=r.get("role"),
                content=[ContentBlock(**c) for c in r.get("content") or []],
                is_sidechain=r.get("is_sidechain", False),
                cwd=r.get("cwd"),
                usage=r.get("usage"),
            )
            for r in rounds_jsonl
        ]

        session = Session(
            session_id=row["session_id"],
            source=row["source"],
            created_at=row["created_at"],
            metadata=row["metadata"],
            rounds=rounds,
        )
        return session, _utc_iso()

