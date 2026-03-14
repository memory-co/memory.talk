"""Message models."""
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
    subject_id: Optional[str] = None
    content: str
    timestamp: datetime
    attachments: list[Attachment] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
