"""Log service — event stream for a card or session (read-only)."""
from __future__ import annotations

from memory_talk_v2.ids import IdKind, InvalidIdError, parse_id
from memory_talk_v2.storage.sqlite import SQLiteStore


class LogError(ValueError):
    pass


class LogNotFound(LogError):
    pass


def log(object_id: str, *, db: SQLiteStore) -> dict:
    try:
        kind, _ = parse_id(object_id)
    except InvalidIdError as e:
        raise LogError(f"invalid id prefix: {e}")
    if kind not in (IdKind.CARD, IdKind.SESSION):
        raise LogError("invalid id prefix")

    if kind == IdKind.CARD:
        if db.get_card(object_id) is None:
            raise LogNotFound(f"card not found: {object_id}")
        key = "card_id"
        type_str = "card"
    else:
        if db.get_session(object_id) is None:
            raise LogNotFound(f"session not found: {object_id}")
        key = "session_id"
        type_str = "session"

    events = db.events_for(object_id)
    return {
        "type": type_str,
        key: object_id,
        "events": [{"at": e["at"], "kind": e["kind"], "detail": e["detail"]} for e in events],
    }
