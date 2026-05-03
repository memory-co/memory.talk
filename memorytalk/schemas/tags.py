"""Tag request/response schemas — kv-shaped, applies to session or card.

`TagPair` is the canonical wire / view representation.  Subject id is in
the URL path (`/v2/{sessions|cards}/{id}/tags`); requests don't carry it.
DELETE doesn't have a body — keys are passed as repeated `?key=` query
params; routes use FastAPI `Query(...)` directly.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TagPair(BaseModel):
    key: str
    value: str = ""


class TagsAddRequest(BaseModel):
    """Body for POST /v2/{subject}/tags. Each item is `key` or `key:value`
    (split on the first `:`)."""
    tags: list[str] = Field(default_factory=list)


class TagsResponse(BaseModel):
    status: str = "ok"
    tags: list[TagPair] = Field(default_factory=list)
