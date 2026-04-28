"""POST /v2/links request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel

from memorytalk.schemas.shared import LinkTargetType


class CreateLinkRequest(BaseModel):
    source_id: str
    source_type: LinkTargetType
    target_id: str
    target_type: LinkTargetType
    comment: str | None = None


class CreateLinkResponse(BaseModel):
    status: str = "ok"
    link_id: str
    ttl: int
