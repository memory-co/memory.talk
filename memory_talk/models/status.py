"""Status models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SourceStatus(BaseModel):
    """Status of a sync source."""
    name: str
    status: str  # running, stopped, error
    messages_synced: int = 0
    last_sync_time: Optional[datetime] = None
    error_message: Optional[str] = None


class ServerStatus(BaseModel):
    """Overall server status."""
    version: str
    sources: list[SourceStatus]
    total_conversations: int
    total_messages: int
    uptime: str
