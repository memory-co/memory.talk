"""Session tag service — add/remove with per-tag change events."""
from __future__ import annotations

from memory_talk_v2.ids import SESSION_PREFIX
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.sqlite import SQLiteStore


class TagServiceError(ValueError):
    """Tag service errors; 400 for prefix/type, 404 for missing session."""


class TagNotFoundError(TagServiceError):
    pass


def _load_session_or_raise(db: SQLiteStore, session_id: str) -> dict:
    if not session_id.startswith(SESSION_PREFIX):
        raise TagServiceError("type mismatch: tag only applies to sessions")
    s = db.get_session(session_id)
    if s is None:
        raise TagNotFoundError(f"session not found: {session_id}")
    return s


def _persist_session_tags(db, sessions_root, session: dict, tags: list[str]) -> None:
    db.update_session_tags(session["session_id"], tags)
    meta = F.read_session_meta(sessions_root, session["source"], session["session_id"]) or {}
    meta["tags"] = tags
    F.write_session_meta(sessions_root, session["source"], session["session_id"], meta)


def add_tags(
    payload: dict, *, db: SQLiteStore, events: EventWriter, sessions_root,
) -> dict:
    session_id = payload.get("session_id") or ""
    incoming = payload.get("tags") or []
    if not isinstance(incoming, list) or not all(isinstance(t, str) and t for t in incoming):
        raise TagServiceError("tags must be a non-empty list of strings")
    if not incoming:
        raise TagServiceError("tags must be non-empty")
    session = _load_session_or_raise(db, session_id)

    existing = set(session["tags"])
    newly_added = [t for t in incoming if t not in existing]
    merged = list(existing.union(incoming))
    # Preserve original ordering + append new ones in request order
    ordered = list(session["tags"]) + [t for t in newly_added if t not in session["tags"]]

    _persist_session_tags(db, sessions_root, session, ordered)

    now_iso = dt_to_iso(now_utc())
    for t in newly_added:
        events.emit(session_id, "tag_added", {"tag": t}, at=now_iso)

    return {"status": "ok", "tags": ordered}


def remove_tags(
    payload: dict, *, db: SQLiteStore, events: EventWriter, sessions_root,
) -> dict:
    session_id = payload.get("session_id") or ""
    incoming = payload.get("tags") or []
    if not isinstance(incoming, list) or not all(isinstance(t, str) and t for t in incoming):
        raise TagServiceError("tags must be a non-empty list of strings")
    if not incoming:
        raise TagServiceError("tags must be non-empty")
    session = _load_session_or_raise(db, session_id)

    existing = list(session["tags"])
    removal_set = set(incoming)
    truly_removed = [t for t in existing if t in removal_set]
    remaining = [t for t in existing if t not in removal_set]

    _persist_session_tags(db, sessions_root, session, remaining)

    now_iso = dt_to_iso(now_utc())
    for t in truly_removed:
        events.emit(session_id, "tag_removed", {"tag": t}, at=now_iso)

    return {"status": "ok", "tags": remaining}
