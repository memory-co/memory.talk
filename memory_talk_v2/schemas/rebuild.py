"""POST /v2/rebuild response schema."""
from __future__ import annotations

from pydantic import BaseModel


class RebuildOut(BaseModel):
    status: str = "ok"
    sessions: int
    cards: int
    searches_replayed: int
    errors_count: int = 0
