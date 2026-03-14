"""Conversation Domain Object."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ConversationDO:
    """Database entity for conversations table."""
    conversation_id: str
    platform: str
    title: str
    created_at: datetime
    updated_at: datetime
    participants: list  # JSON stored as list
    message_count: int
