"""POST /v3/recall — request + response.

Minimal output by design — recall feeds the LLM's context-window budget,
so per-card payload is just ``card_id + insight``. Anything richer (rounds /
stats / source_cards) goes through ``POST /v3/read`` when the LLM wants
to expand a hit.
"""
from __future__ import annotations
from pydantic import BaseModel, Field


class RecallRequest(BaseModel):
    # Can be raw platform id OR a `sess_`-prefixed id; the server
    # normalizes either way. Recall runs at hook time before sync has
    # necessarily caught up, so the server does NOT require the session
    # to exist in the DB — the id is just a dedup key here.
    session_id: str
    prompt: str
    top_k: int | None = None  # falls back to settings.recall.default_top_k


class RecalledCard(BaseModel):
    card_id: str
    insight: str


class RecallResponse(BaseModel):
    session_id: str  # normalized (prefixed)
    query: str
    recalled: list[RecalledCard] = Field(default_factory=list)
    # Card ids that *would* have matched but are already in this session's
    # recall_log — exposed so callers can see what was filtered out.
    skipped_already_recalled: list[str] = Field(default_factory=list)
