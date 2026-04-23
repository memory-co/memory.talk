"""Log service — read-only event stream from the object's own events.jsonl."""
from __future__ import annotations

from memory_talk_v2.config import Config
from memory_talk_v2.ids import IdKind, InvalidIdError, parse_id
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.sqlite import SQLiteStore


class LogError(ValueError):
    pass


class LogNotFound(LogError):
    pass


def log(object_id: str, *, config: Config, db: SQLiteStore) -> dict:
    try:
        kind, _ = parse_id(object_id)
    except InvalidIdError as e:
        raise LogError(f"invalid id prefix: {e}")
    if kind not in (IdKind.CARD, IdKind.SESSION):
        raise LogError("invalid id prefix")

    if kind == IdKind.CARD:
        if db.get_card(object_id) is None:
            raise LogNotFound(f"card not found: {object_id}")
        events = F.read_card_events(config.cards_dir, object_id)
        key, type_str = "card_id", "card"
    else:
        session = db.get_session(object_id)
        if session is None:
            raise LogNotFound(f"session not found: {object_id}")
        events = F.read_session_events(config.sessions_dir, session["source"], object_id)
        key, type_str = "session_id", "session"

    events.sort(key=lambda e: e["at"])
    return {
        "type": type_str,
        key: object_id,
        "events": [{"at": e["at"], "kind": e["kind"], "detail": e["detail"]} for e in events],
    }
