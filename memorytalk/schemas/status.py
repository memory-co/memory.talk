"""GET /v3/status — response."""
from __future__ import annotations

from pydantic import BaseModel


class StatusResponse(BaseModel):
    data_root: str
    settings_path: str
    status: str
    sessions_total: int
    # Real v4 cards (the governed question graph). 0 until the mark
    # write-path builds the graph.
    cards_total: int
    # Migrated v3 knowledge (read-only insights). Counted separately so
    # the legacy figure stays visible, correctly labeled.
    insights_total: int
    reviews_total: int
    searches_total: int
    recalls_total: int
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    vector_provider: str
    relation_provider: str
    sync_enabled: bool
    # Present only while a searchbase reembed is running: ``status`` flips
    # to ``"reembedding"`` and this carries the rows re-embedded so far.
    # Omitted (``None``) in the normal ``"running"`` state.
    reembed_processed: int | None = None
