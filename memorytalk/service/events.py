"""EventWriter — append a lifecycle event to a session or card events.jsonl.

These events back the audit / lifeline view of an object; services call
this whenever they perform a state-affecting operation on the parent
object (card created, card read, card reviewed, session imported, ...).
"""
from __future__ import annotations
import datetime as _dt
from typing import Any

from memorytalk.repository import SQLiteStore


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class EventWriter:
    def __init__(self, db: SQLiteStore):
        self.db = db

    async def session_event(
        self, source: str, session_id: str, event: str, **detail: Any
    ) -> None:
        await self.db.sessions.append_event(
            source, session_id,
            {"event": event, "ts": _utc_iso(), **detail},
        )

    async def card_event(self, card_id: str, event: str, **detail: Any) -> None:
        """v4 card lifecycle event (created / position_added / reviewed /
        card_linked / session_cited / vector_index_failed)."""
        await self.db.cards.append_event(
            card_id,
            {"event": event, "ts": _utc_iso(), **detail},
        )
