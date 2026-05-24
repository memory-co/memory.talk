"""ReviewService — POST /v3/reviews.

The structural counterpart to CardService.create — but for *attaching
a stance* (with evidence) to an already-existing card.

Side-effect chain (mirrors the cards / sessions pattern):

  1. SQLite:   `reviews` row insert
  2. SQLite:   `card_stats` bump (review_up / review_down / review_neutral
               + review_count, all in one atomic UPDATE)
  3. File:     append to ``cards/<bucket>/<card_id>/reviews.jsonl``
  4. Event:    `reviewed` to ``cards/<bucket>/<card_id>/events.jsonl``

Reviews are append-only — no edit / delete contract. To "change your
mind" the contract is to write a follow-up review with the new score
(the forum-dynamics 沉浮 公式 looks at the cumulative ↑↓ counts, so a
later review pulling toward 0 acts as the correction).
"""
from __future__ import annotations
import datetime as _dt

from memorytalk.repository import SQLiteStore
from memorytalk.schemas import CreateReviewRequest
from memorytalk.service.events import EventWriter
from memorytalk.util.ids import (
    CARD_PREFIX, REVIEW_PREFIX, SESSION_PREFIX, SESSION_PREFIX_LEGACY,
    new_review_id,
)
from memorytalk.util.indexes import IndexesParseError, parse_indexes


class ReviewServiceError(Exception):
    """4xx: validation failed."""


class ReviewConflict(ReviewServiceError):
    """409: supplied review_id already taken."""


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class ReviewService:
    def __init__(self, db: SQLiteStore, events: EventWriter):
        self.db = db
        self.events = events

    async def create(self, req: CreateReviewRequest) -> dict:
        if req.score not in (-1, 0, 1):
            raise ReviewServiceError("score must be one of 1, 0, -1")
        if not req.card_id or not req.card_id.startswith(CARD_PREFIX):
            raise ReviewServiceError("invalid card_id prefix")
        if not req.session_id or not req.session_id.startswith((SESSION_PREFIX, SESSION_PREFIX_LEGACY)):
            raise ReviewServiceError("invalid session_id prefix")

        # Card existence + session existence + indexes range.
        if not await self.db.cards.exists(req.card_id):
            raise ReviewServiceError(f"card {req.card_id} not found")
        session_row = await self.db.sessions.get(req.session_id)
        if session_row is None:
            raise ReviewServiceError(f"session {req.session_id} not found")
        try:
            want = parse_indexes(req.indexes)
        except IndexesParseError as e:
            raise ReviewServiceError(str(e)) from e
        round_count = session_row["round_count"]
        for idx in want:
            if not 1 <= idx <= round_count:
                raise ReviewServiceError(
                    f"index {idx} out of range for session {req.session_id}"
                )

        # Resolve review_id (auto or supplied + uniqueness check).
        review_id = req.review_id or new_review_id()
        if not review_id.startswith(REVIEW_PREFIX):
            raise ReviewServiceError("invalid review_id prefix")
        if req.review_id and await self.db.reviews.exists(review_id):
            raise ReviewConflict(f"review_id {review_id} already exists")

        now = _utc_iso()

        # ── 1. SQL: reviews row ──────────────────────────────────────────
        await self.db.reviews.insert(
            review_id=review_id, card_id=req.card_id,
            session_id=req.session_id, indexes=req.indexes,
            score=req.score, comment=req.comment, created_at=now,
        )

        # ── 2. SQL: card_stats bump ─────────────────────────────────────
        await self.db.cards.bump_review(req.card_id, req.score, now)

        # ── 3. File mirror ──────────────────────────────────────────────
        await self.db.cards.append_review_mirror(req.card_id, {
            "review_id": review_id, "card_id": req.card_id,
            "session_id": req.session_id, "indexes": req.indexes,
            "score": req.score, "comment": req.comment,
            "created_at": now,
        })

        # ── 4. Event ─────────────────────────────────────────────────────
        await self.events.card_event(
            req.card_id, "reviewed",
            review_id=review_id, score=req.score,
            session_id=req.session_id, indexes=req.indexes,
        )

        return {
            "review_id": review_id, "card_id": req.card_id,
            "session_id": req.session_id, "score": req.score,
        }
