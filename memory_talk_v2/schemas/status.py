"""GET /v2/status response schema."""
from __future__ import annotations

from pydantic import BaseModel


class StatusOut(BaseModel):
    data_root: str
    settings_path: str
    status: str = "running"
    sessions_total: int
    cards_total: int
    links_total: int
    searches_total: int
    vector_provider: str
    relation_provider: str
    embedding_provider: str
