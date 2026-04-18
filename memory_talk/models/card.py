"""Talk-Card data model — the core memory unit."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class CardRound(BaseModel):
    role: str
    text: str
    thinking: Optional[str] = None

class CardLinkInput(BaseModel):
    id: str
    type: str
    comment: Optional[str] = None

class TalkCard(BaseModel):
    card_id: str
    summary: str
    session_id: Optional[str] = None
    rounds: list[CardRound]
    links: list[CardLinkInput] = []
    ttl: int = 0
    created_at: datetime = datetime.now()
