"""Session model — a standardized conversation from any platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from .round import Round


class Session(BaseModel):
    session_id: str
    source: str  # platform identifier (claude-code / codex / openclaw)
    created_at: Optional[datetime] = None
    metadata: dict[str, Any] = {}
    rounds: list[Round] = []
