"""EventWriter — append events to each object's own events.jsonl.

Every card and every session carries its own append-only event stream at:

  cards/<bucket>/<card_id>/events.jsonl
  sessions/<source>/<bucket>/<sess_*>/events.jsonl

These files ARE the event log. No SQLite event_log table, no global dated
jsonl — the file path encodes the object identity, and rebuild is a no-op
for events (they already live in the right place).

A two-end `linked` event produces two append calls — one on each endpoint's
file, each with its own event_id.
"""
from __future__ import annotations

from memory_talk_v2.config import Config
from memory_talk_v2.ids import CARD_PREFIX, SESSION_PREFIX, new_event_id
from memory_talk_v2.service.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.sqlite import SQLiteStore


class EventWriter:
    def __init__(self, config: Config, db: SQLiteStore):
        self.config = config
        self.db = db

    def emit(self, object_id: str, kind: str, detail: dict, at: str | None = None) -> str:
        event_id = new_event_id()
        at_iso = at or dt_to_iso(now_utc())
        record = {"event_id": event_id, "at": at_iso, "kind": kind, "detail": detail}

        if object_id.startswith(CARD_PREFIX):
            F.append_card_event(self.config.cards_dir, object_id, record)
        elif object_id.startswith(SESSION_PREFIX):
            session = self.db.get_session(object_id)
            if session is None:
                raise ValueError(f"cannot emit event for unknown session: {object_id}")
            F.append_session_event(
                self.config.sessions_dir, session["source"], object_id, record,
            )
        else:
            raise ValueError(f"unknown object prefix: {object_id}")
        return event_id
