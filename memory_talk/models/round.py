"""Round model — one turn in a conversation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .content_block import ContentBlock


class Round(BaseModel):
    round_id: str
    timestamp: Optional[datetime] = None
    speaker: str  # physical identity (who)
    role: str  # logical identity (human / assistant / system / tool)
    content: list[ContentBlock]
