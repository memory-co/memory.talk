"""EventWriter — dual write event_log rows to jsonl (truth) + SQLite (index).

jsonl first, SQLite second. rebuild replays jsonl into SQLite so as long as
jsonl is written the event is not lost.
"""
from __future__ import annotations

from memory_talk_v2.ids import new_event_id
from memory_talk_v2.service.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage.jsonl_writer import DatedJsonlWriter
from memory_talk_v2.storage.sqlite import SQLiteStore


class EventWriter:
    def __init__(self, jsonl: DatedJsonlWriter, db: SQLiteStore):
        self.jsonl = jsonl
        self.db = db

    def emit(self, object_id: str, kind: str, detail: dict, at: str | None = None) -> str:
        event_id = new_event_id()
        object_kind = "card" if object_id.startswith("card_") else "session"
        at_iso = at or dt_to_iso(now_utc())
        row = {
            "event_id": event_id,
            "object_id": object_id,
            "object_kind": object_kind,
            "at": at_iso,
            "kind": kind,
            "detail": detail,
        }
        self.jsonl.append(row)
        self.db.insert_event(event_id, object_id, object_kind, at_iso, kind, detail)
        return event_id
