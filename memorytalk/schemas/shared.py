"""Shared Pydantic types used across multiple endpoint schemas."""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, Field


LinkTargetType = Literal["card", "session"]
ObjectKind = Literal["card", "session"]


class ContentBlock(BaseModel):
    type: str  # text / code / thinking / ...
    text: str | None = None
    thinking: str | None = None
    language: str | None = None


class SessionRound(BaseModel):
    """Round as it appears in a Session (full fidelity)."""
    index: int
    round_id: str
    parent_id: str | None = None
    timestamp: str | None = None
    speaker: str | None = None
    role: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    is_sidechain: bool = False
    cwd: str | None = None
    usage: dict[str, Any] | None = None


class CardRound(BaseModel):
    """Round as it appears in a Card (flattened)."""
    role: str
    text: str
    thinking: str | None = None
    session_id: str
    index: int


class LinkRef(BaseModel):
    """Link in view/search responses (from the perspective of one endpoint)."""
    link_id: str
    target_id: str
    target_type: LinkTargetType
    comment: str | None = None
    ttl: int
