"""Link service — create user links; helpers for reading links touching an object."""
from __future__ import annotations
from datetime import datetime

from memorytalk.config import Config
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import CreateLinkRequest, CreateLinkResponse, LinkRef
from memorytalk.service.events import EventWriter
from memorytalk.util.ids import CARD_PREFIX, SESSION_PREFIX, new_link_id
from memorytalk.util.ttl import (
    current_ttl, dt_to_iso, initial_expires_at, iso_to_dt, now_utc, refresh,
)


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


def link_to_ref(link: dict, object_id: str, now: datetime) -> LinkRef:
    if link["source_id"] == object_id:
        peer_id = link["target_id"]
        peer_type = link["target_type"]
    else:
        peer_id = link["source_id"]
        peer_type = link["source_type"]
    return LinkRef(
        link_id=link["link_id"],
        target_id=peer_id,
        target_type=peer_type,
        comment=link["comment"],
        ttl=current_ttl(link["expires_at"], now),
    )


async def refresh_active_user_links(
    db: SQLiteStore, links: list[dict], factor: float, max_seconds: int, now: datetime,
) -> None:
    for l in links:
        if l["expires_at"] is None:
            continue
        remaining = (iso_to_dt(l["expires_at"]) - now).total_seconds()
        if remaining <= 0:
            continue
        new_exp = refresh(l["expires_at"], factor, max_seconds, now=now)
        if new_exp != l["expires_at"]:
            await db.links.update_expires_at(l["link_id"], new_exp)
            l["expires_at"] = new_exp


class LinkService:
    def __init__(self, *, config: Config, db: SQLiteStore, events: EventWriter):
        self.config = config
        self.db = db
        self.events = events

    async def create(self, payload: CreateLinkRequest) -> CreateLinkResponse:
        source_id = payload.source_id
        source_type = payload.source_type
        target_id = payload.target_id
        target_type = payload.target_type
        comment = payload.comment

        if not (_prefix_matches(source_id, source_type) and _prefix_matches(target_id, target_type)):
            raise LinkServiceError("invalid id prefix or type mismatch")
        if source_id == target_id:
            raise LinkServiceError("self-loop not allowed")
        if comment is not None and len(comment) > self.config.settings.search.comment_max_length:
            raise LinkServiceError("comment too long")

        if not await self._object_exists(source_id, source_type):
            raise LinkNotFoundError(f"source not found: {source_id}")
        if not await self._object_exists(target_id, target_type):
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
        await self.db.links.write_doc(link_doc)
        await self.db.links.insert(
            link_id=link_id, source_id=source_id, source_type=source_type,
            target_id=target_id, target_type=target_type, comment=comment,
            expires_at=expires_at, created_at=created_at,
        )

        await self.events.emit(source_id, "linked", {
            "direction": "outgoing", "link_id": link_id,
            "peer_id": target_id, "peer_type": target_type,
            "comment": comment, "ttl_initial": ttl_initial,
        }, at=created_at)
        await self.events.emit(target_id, "linked", {
            "direction": "incoming", "link_id": link_id,
            "peer_id": source_id, "peer_type": source_type,
            "comment": comment, "ttl_initial": ttl_initial,
        }, at=created_at)

        return CreateLinkResponse(status="ok", link_id=link_id, ttl=ttl_initial)

    async def _object_exists(self, object_id: str, type_str: str) -> bool:
        if type_str == "card":
            return (await self.db.cards.get(object_id)) is not None
        if type_str == "session":
            return (await self.db.sessions.get(object_id)) is not None
        return False
