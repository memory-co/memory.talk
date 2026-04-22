"""View service — prefix-dispatched read with TTL refresh.

Design decisions (spec §3.6):
- card_ → refresh card.expires_at; user links (ttl > 0) touching card are refreshed.
  Default links (expires_at IS NULL) and expired (<=0) user links are not.
- sess_ → session has no TTL; only user links touching it are refreshed.
- No event emission, no view.jsonl.
"""
from __future__ import annotations

from memory_talk_v2.config import Config
from memory_talk_v2.ids import CARD_PREFIX, SESSION_PREFIX, IdKind, parse_id, InvalidIdError
from memory_talk_v2.service.ttl import current_ttl, dt_to_iso, iso_to_dt, now_utc, refresh
from memory_talk_v2.storage.sqlite import SQLiteStore


class ViewError(ValueError):
    pass


class ViewNotFound(ViewError):
    pass


def _link_to_ref(link: dict, object_id: str, now) -> dict:
    """From the object's perspective, the 'other side' is the peer."""
    if link["source_id"] == object_id:
        peer_id = link["target_id"]
        peer_type = link["target_type"]
    else:
        peer_id = link["source_id"]
        peer_type = link["source_type"]
    return {
        "link_id": link["link_id"],
        "target_id": peer_id,
        "target_type": peer_type,
        "comment": link["comment"],
        "ttl": current_ttl(link["expires_at"], now),
    }


def _refresh_active_user_links(db: SQLiteStore, links: list[dict], config: Config, now) -> None:
    factor = config.settings.ttl.link.factor
    max_s = config.settings.ttl.link.max
    for l in links:
        if l["expires_at"] is None:
            continue  # default link sentinel
        remaining = (iso_to_dt(l["expires_at"]) - now).total_seconds()
        if remaining <= 0:
            continue  # expired: do not revive
        new_exp = refresh(l["expires_at"], factor, max_s, now=now)
        if new_exp != l["expires_at"]:
            db.update_link_expires_at(l["link_id"], new_exp)
            l["expires_at"] = new_exp


def view(object_id: str, *, config: Config, db: SQLiteStore) -> dict:
    try:
        kind, _ = parse_id(object_id)
    except InvalidIdError as e:
        raise ViewError(f"invalid id prefix: {e}")

    if kind not in (IdKind.CARD, IdKind.SESSION):
        raise ViewError("invalid id prefix")

    now = now_utc()
    read_at = dt_to_iso(now)

    if kind == IdKind.CARD:
        card = db.get_card(object_id)
        if card is None:
            raise ViewNotFound(f"card not found: {object_id}")

        # Refresh card TTL
        new_exp = refresh(
            card["expires_at"],
            config.settings.ttl.card.factor,
            config.settings.ttl.card.max,
            now=now,
        )
        if new_exp != card["expires_at"]:
            db.update_card_expires_at(object_id, new_exp)
            card["expires_at"] = new_exp

        links = db.links_touching(object_id)
        _refresh_active_user_links(db, links, config, now)

        return {
            "type": "card",
            "read_at": read_at,
            "card": {
                "card_id": card["card_id"],
                "summary": card["summary"],
                "rounds": card["rounds"],
                "created_at": card["created_at"],
                "ttl": current_ttl(card["expires_at"], now),
            },
            "links": [_link_to_ref(l, object_id, now) for l in links],
        }

    # SESSION
    session = db.get_session(object_id)
    if session is None:
        raise ViewNotFound(f"session not found: {object_id}")
    rounds = db.list_rounds(object_id)

    links = db.links_touching(object_id)
    _refresh_active_user_links(db, links, config, now)

    return {
        "type": "session",
        "read_at": read_at,
        "session": {
            "session_id": session["session_id"],
            "source": session["source"],
            "created_at": session["created_at"],
            "tags": session["tags"],
            "metadata": session["metadata"],
            "rounds": [{
                "index": r["idx"], "round_id": r["round_id"], "parent_id": r["parent_id"],
                "timestamp": r["timestamp"], "speaker": r["speaker"], "role": r["role"],
                "content": r["content"], "is_sidechain": r["is_sidechain"],
                "cwd": r["cwd"], "usage": r["usage"],
            } for r in rounds],
        },
        "links": [_link_to_ref(l, object_id, now) for l in links],
    }
