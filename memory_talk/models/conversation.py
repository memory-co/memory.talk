"""Conversation models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class Participant(BaseModel):
    """A participant in a conversation."""
    name: str
    role: str
    model: Optional[str] = None


class ConversationMetadata(BaseModel):
    """Conversation metadata."""
    session_id: str
    platform: str
    title: str
    created_at: datetime
    updated_at: datetime
    participants: list[Participant]
    message_count: int


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""
    session_id: str
    platform: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
