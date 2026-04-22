"""User link creation service — validate prefixes, write dual events."""
from __future__ import annotations

from memory_talk_v2.config import Config
from memory_talk_v2.ids import CARD_PREFIX, SESSION_PREFIX, new_link_id
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.ttl import dt_to_iso, initial_expires_at, now_utc
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.sqlite import SQLiteStore


class LinkServiceError(ValueError):
    """Raised by the link service; 400 for validation, 404 for missing objects."""


class LinkNotFoundError(LinkServiceError):
    pass


def _prefix_matches(id_str: str, type_str: str) -> bool:
    if type_str == "card":
        return id_str.startswith(CARD_PREFIX)
    if type_str == "session":
        return id_str.startswith(SESSION_PREFIX)
    return False


def _object_exists(db: SQLiteStore, id_str: str, type_str: str) -> bool:
    if type_str == "card":
        return db.get_card(id_str) is not None
    if type_str == "session":
        return db.get_session(id_str) is not None
    return False


def create_user_link(
    payload: dict,
    *,
    config: Config,
    db: SQLiteStore,
    events: EventWriter,
) -> dict:
    source_id = payload.get("source_id") or ""
    source_type = payload.get("source_type") or ""
    target_id = payload.get("target_id") or ""
    target_type = payload.get("target_type") or ""
    comment = payload.get("comment")

    if not (_prefix_matches(source_id, source_type) and _prefix_matches(target_id, target_type)):
        raise LinkServiceError("invalid id prefix or type mismatch")
    if source_id == target_id:
        raise LinkServiceError("self-loop not allowed")

    if comment is not None and len(comment) > config.settings.search.comment_max_length:
        raise LinkServiceError("comment too long")

    if not _object_exists(db, source_id, source_type):
        raise LinkNotFoundError(f"source not found: {source_id}")
    if not _object_exists(db, target_id, target_type):
        raise LinkNotFoundError(f"target not found: {target_id}")

    now = now_utc()
    created_at = dt_to_iso(now)
    ttl_initial = config.settings.ttl.link.initial
    expires_at = initial_expires_at(ttl_initial, now=now)
    link_id = new_link_id()

    link_doc = {
        "link_id": link_id,
        "source_id": source_id,
        "source_type": source_type,
        "target_id": target_id,
        "target_type": target_type,
        "comment": comment,
        "expires_at": expires_at,
        "created_at": created_at,
    }
    F.write_link(config.links_dir, link_doc)
    db.insert_link(
        link_id=link_id, source_id=source_id, source_type=source_type,
        target_id=target_id, target_type=target_type, comment=comment,
        expires_at=expires_at, created_at=created_at,
    )

    # Two-end events: outgoing on source, incoming on target
    events.emit(source_id, "linked", {
        "direction": "outgoing", "link_id": link_id,
        "peer_id": target_id, "peer_type": target_type,
        "comment": comment, "ttl_initial": ttl_initial,
    }, at=created_at)
    events.emit(target_id, "linked", {
        "direction": "incoming", "link_id": link_id,
        "peer_id": source_id, "peer_type": source_type,
        "comment": comment, "ttl_initial": ttl_initial,
    }, at=created_at)

    return {"status": "ok", "link_id": link_id, "ttl": ttl_initial}
