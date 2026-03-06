"""Data models for talk-memory server."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Attachment(BaseModel):
    """Attachment metadata."""
    hash: str
    name: str
    size: int
    mime: str


class Message(BaseModel):
    """A single message in a conversation."""
    uuid: str
    parent_uuid: Optional[str] = None
    role: str
    content: str
    timestamp: datetime
    attachments: list[Attachment] = Field(default_factory=list)


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


class IngestRequest(BaseModel):
    """Request body for /api/ingest."""
    platform: str
    session_id: str
    messages: list[Message]
    metadata: dict = Field(default_factory=dict)


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""
    session_id: str
    platform: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class SearchResult(BaseModel):
    """Search result item."""
    session_id: str
    platform: str
    title: str
    matched_message: str
    timestamp: datetime
