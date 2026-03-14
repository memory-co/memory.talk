"""Message Domain Object."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MessageDO:
    """Database entity for messages table."""
    uuid: str
    parent_uuid: Optional[str]
    platform: str
    conversation_id: str
    role: str
    subject_id: Optional[str]
    content: str
    timestamp: datetime
    attachments: list  # JSON stored as list
    metadata: dict     # JSON stored as dict
