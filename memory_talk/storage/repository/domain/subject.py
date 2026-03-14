"""Subject Domain Object."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SubjectDO:
    """Database entity for subjects table."""
    id: str
    name: str
    match: Optional[str] = None  # jinja2 expression to match platform/role
    priority: int = 0           # higher priority = matched first
    metadata: dict              # JSON stored as dict
    created_at: datetime
    updated_at: datetime
