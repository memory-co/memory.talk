"""Link service — create user links; helpers for reading links touching an object.

Also exports the shared `link_to_ref` and `refresh_active_user_links` helpers
used by SessionService and CardService during their view() paths.
"""
from __future__ import annotations
from datetime import datetime

from memory_talk_v2.config import Config
from memory_talk_v2.ids import CARD_PREFIX, SESSION_PREFIX, new_link_id
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.ttl import (
    current_ttl, dt_to_iso, initial_expires_at, iso_to_dt, now_utc, refresh,
)
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.sqlite import SQLiteStore


class LinkServiceError(ValueError):
    """400 — validation failures."""


class LinkNotFoundError(LinkServiceError):
    """404 — one endpoint of the link doesn't exist."""


def _prefix_matches(id_str: str, type_str: str) -> bool:
    if type_str == "card":
        return id_str.startswith(CARD_PREFIX)
    if type_str == "session":
        return id_str.startswith(SESSION_PREFIX)
    return False


def link_to_ref(link: dict, object_id: str, now: datetime) -> dict:
    """From the given object's perspective, render a link row as a LinkRef."""
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


def refresh_active_user_links(
    db: SQLiteStore, links: list[dict], factor: float, max_seconds: int, now: datetime,
) -> None:
    """Refresh in-place. Default links (expires_at IS NULL) and expired user
    links (remaining <= 0) are not refreshed."""
    for l in links:
        if l["expires_at"] is None:
            continue
        remaining = (iso_to_dt(l["expires_at"]) - now).total_seconds()
        if remaining <= 0:
            continue
        new_exp = refresh(l["expires_at"], factor, max_seconds, now=now)
        if new_exp != l["expires_at"]:
            db.update_link_expires_at(l["link_id"], new_exp)
            l["expires_at"] = new_exp


class LinkService:
    def __init__(self, *, config: Config, db: SQLiteStore, events: EventWriter):
        self.config = config
        self.db = db
        self.events = events

    def create(self, payload: dict) -> dict:
        source_id = payload.get("source_id") or ""
        source_type = payload.get("source_type") or ""
        target_id = payload.get("target_id") or ""
        target_type = payload.get("target_type") or ""
        comment = payload.get("comment")

        if not (_prefix_matches(source_id, source_type) and _prefix_matches(target_id, target_type)):
            raise LinkServiceError("invalid id prefix or type mismatch")
        if source_id == target_id:
            raise LinkServiceError("self-loop not allowed")
        if comment is not None and len(comment) > self.config.settings.search.comment_max_length:
            raise LinkServiceError("comment too long")

        if not self._object_exists(source_id, source_type):
            raise LinkNotFoundError(f"source not found: {source_id}")
        if not self._object_exists(target_id, target_type):
            raise LinkNotFoundError(f"target not found: {target_id}")

        now = now_utc()
        created_at = dt_to_iso(now)
        ttl_initial = self.config.settings.ttl.link.initial
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
        F.write_link(self.config.links_dir, link_doc)
        self.db.insert_link(
            link_id=link_id, source_id=source_id, source_type=source_type,
            target_id=target_id, target_type=target_type, comment=comment,
            expires_at=expires_at, created_at=created_at,
        )

        # Two-end events
        self.events.emit(source_id, "linked", {
            "direction": "outgoing", "link_id": link_id,
            "peer_id": target_id, "peer_type": target_type,
            "comment": comment, "ttl_initial": ttl_initial,
        }, at=created_at)
        self.events.emit(target_id, "linked", {
            "direction": "incoming", "link_id": link_id,
            "peer_id": source_id, "peer_type": source_type,
            "comment": comment, "ttl_initial": ttl_initial,
        }, at=created_at)

        return {"status": "ok", "link_id": link_id, "ttl": ttl_initial}

    def _object_exists(self, object_id: str, type_str: str) -> bool:
        if type_str == "card":
            return self.db.get_card(object_id) is not None
        if type_str == "session":
            return self.db.get_session(object_id) is not None
        return False
