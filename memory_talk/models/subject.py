"""Subject models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Subject(BaseModel):
    """Subject - 可独立管理的实体表，平等但通过规则区分"""
    id: str
    name: str
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
