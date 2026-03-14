"""API request/response models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from memory_talk.models.message import Message


class IngestRequest(BaseModel):
    """Request body for /api/ingest."""
    platform: str
    conversation_id: str
    messages: list[Message]
    metadata: dict = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Search result item."""
    conversation_id: str
    platform: str
    title: str
    matched_message: str
    timestamp: datetime
