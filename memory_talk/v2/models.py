"""v2 Pydantic models.

Minimal shell — only the shared types used across multiple v2 services
and the persisted log schemas. Request / response models for individual
endpoints live with their services (future plans).
"""
from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel


LinkTargetType = Literal["card", "session"]
ObjectKind = Literal["card", "session"]


class LinkRef(BaseModel):
    """A link as it appears in view/search responses (from the perspective of
    the object being read)."""
    link_id: str
    target_id: str
    target_type: LinkTargetType
    comment: str | None = None
    ttl: int  # seconds; 0 = default link sentinel; <0 = expired


class SearchLog(BaseModel):
    """Persisted full-response audit record for a /v2/search call."""
    search_id: str
    query: str
    where: str | None
    top_k: int
    created_at: str
    cards: dict[str, Any]
    sessions: dict[str, Any]


class EventLog(BaseModel):
    """Single row in event_log — the wire shape for /v2/log events."""
    event_id: str
    object_id: str  # prefixed id (card_* or sess_*)
    object_kind: ObjectKind
    at: str
    kind: str  # event kind (imported, rounds_appended, tag_added, linked, created, ...)
    detail: dict[str, Any]
