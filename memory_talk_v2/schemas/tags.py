"""POST /v2/tags/{add,remove} request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel


class TagsIn(BaseModel):
    session_id: str
    tags: list[str]


class TagsOut(BaseModel):
    status: str = "ok"
    tags: list[str]
