"""Link data model — relationship between any two objects."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class Link(BaseModel):
    link_id: str
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    comment: Optional[str] = None
    ttl: int = 0
    created_at: datetime = datetime.now()

class LinkCreate(BaseModel):
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    comment: Optional[str] = None
