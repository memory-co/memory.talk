"""EventWriter — append events to each object's own events.jsonl (async).

Every card and every session carries its own append-only event stream at:
  cards/<bucket>/<card_id>/events.jsonl
  sessions/<source>/<bucket>/<sess_*>/events.jsonl
"""
from __future__ import annotations

from memory_talk_v2.config import Config
from memory_talk_v2.util.ids import CARD_PREFIX, SESSION_PREFIX, new_event_id
from memory_talk_v2.util.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage import files as F
from memory_talk_v2.repository import SQLiteStore


class EventWriter:
    def __init__(self, config: Config, db: SQLiteStore):
        self.config = config
        self.db = db

    async def emit(self, object_id: str, kind: str, detail: dict, at: str | None = None) -> str:
        event_id = new_event_id()
        at_iso = at or dt_to_iso(now_utc())
        record = {"event_id": event_id, "at": at_iso, "kind": kind, "detail": detail}

        if object_id.startswith(CARD_PREFIX):
            await F.append_card_event(self.config.cards_dir, object_id, record)
        elif object_id.startswith(SESSION_PREFIX):
            session = await self.db.sessions.get(object_id)
            if session is None:
                raise ValueError(f"cannot emit event for unknown session: {object_id}")
            await F.append_session_event(
                self.config.sessions_dir, session["source"], object_id, record,
            )
        else:
            raise ValueError(f"unknown object prefix: {object_id}")
        return event_id
