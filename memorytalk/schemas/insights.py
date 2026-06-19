"""GET /v4/insights — read-only list/search response shapes.

Insight is the renamed v3 card, kept read-only in v4 (data preserved).
Only the list shape survives; create / tag / delete request+response
models are gone with the write surface.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from memorytalk.schemas.insight import InsightStats


class InsightMeta(BaseModel):
    """One row in ``GET /v4/insights``.

    Metadata-only (no expanded ``rounds`` — ``read <insight_id>`` covers
    full content) plus stats + tags.
    """
    insight_id: str
    insight: str
    created_at: str
    tags: dict[str, str] = Field(default_factory=dict)
    stats: InsightStats = Field(default_factory=InsightStats)


class InsightListResponse(BaseModel):
    total: int
    returned: int
    cards: list[InsightMeta] = Field(default_factory=list)
