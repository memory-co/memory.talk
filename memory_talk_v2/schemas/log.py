"""POST /v2/log request/response schemas."""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, Field


class LogRequest(BaseModel):
    id: str


class EventEntry(BaseModel):
    at: str
    kind: str
    detail: dict[str, Any]


class LogResponse(BaseModel):
    type: Literal["card", "session"]
    card_id: str | None = None
    session_id: str | None = None
    events: list[EventEntry] = Field(default_factory=list)
