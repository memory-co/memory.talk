"""ReadService — prefix-dispatched read of card or session.

The CLI / API layer parses the id prefix and calls one of:
- ``read_insight(card_id)`` → full Insight with stats, source_cards, reviews, rounds
- ``read_session(session_id)`` → full Session with rounds (read from jsonl)

Insight reads have a side effect: ``card.stats.read_count`` is bumped by one
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
    Insight, InsightRound, InsightStats, ContentBlock, Round, Session, SourceInsight,
)
from memorytalk.schemas.session import SessionMark
# InsightNotFound is owned by service.cards (the card service is the canonical
# place for card lifecycle errors); re-exported here for callers that
# historically imported it from service.read.
from memorytalk.service.insights import InsightNotFound
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

    async def read_insight(self, insight_id: str) -> tuple[Insight, str]:
        """Return (insight, read_at). Insight is READ-ONLY in v4 — this is a
        pure read: no read_count bump, no event written."""
        row = await self.db.insights.get(insight_id)
        if row is None:
            raise InsightNotFound(f"insight {insight_id} not found")

        now = _utc_iso()
        stats_dict = await self.db.insights.get_stats(insight_id)
        # Merge in derived recall_count (single source of truth lives in
        # recall_event; insight_stats no longer carries the column).
        counts = await self.db.recall.recall_counts([insight_id])
        stats_dict["recall_count"] = counts.get(insight_id, 0)
        source_cards = await self.db.insights.list_source_cards(insight_id)

        insight = Insight(
            insight_id=row["insight_id"],
            insight=row["insight"],
            source_cards=[SourceInsight(**sc) for sc in source_cards],
            rounds=[InsightRound(**r) for r in row["rounds"]],
            stats=InsightStats(**stats_dict),
            created_at=row["created_at"],
        )
        return insight, now

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

        # Fold in the session's marks: metadata from session_marks (ordered
        # m1,m2,…) + each mark's canonical YAML for the full body (description /
        # mark text / indexes / resolved issues→cards). The reading is pure —
        # this is just a join over already-written derived state.
        marks = await self._read_marks(row["source"], session_id)

        session = Session(
            session_id=row["session_id"],
            source=row["source"],
            created_at=row["created_at"],
            metadata=row["metadata"],
            rounds=rounds,
            marks=marks,
        )
        return session, _utc_iso()

    async def _read_marks(self, source: str, session_id: str) -> list[SessionMark]:
        """Build the session's ``marks[]`` for the session read: ``session_marks``
        metadata (ordered m1,m2,…) joined with each mark's canonical YAML body
        (per-round ``rounds[]`` with resolved issues→cards)."""
        rows = await self.db.session_marks.list_for_session(session_id)
        marks: list[SessionMark] = []
        for r in rows:
            body = await self.db.session_mark_files.read_doc(
                source, session_id, r["mark"],
            ) or {}
            marks.append(SessionMark(
                mark=r["mark"],
                description=body.get("description", ""),
                last_index=body.get("last_index") or r.get("last_index") or 0,
                rounds=body.get("rounds") or [],
                created_at=body.get("created_at") or r.get("created_at") or "",
            ))
        return marks

