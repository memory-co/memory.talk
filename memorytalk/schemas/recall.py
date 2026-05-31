"""POST /v3/recall + GET /v3/recall/sessions + GET /v3/recall/sessions/{sid}.

Minimal hook payload by design — recall feeds the LLM's context-window
budget, so per-card payload is just ``card_id + insight``. Anything
richer (rounds / stats / source_cards) goes through ``POST /v3/read``
when the LLM wants to expand a hit.

See ``docs/cli/v3/recall.md`` and ``docs/structure/v3/recall.md``.
"""
from __future__ import annotations
from pydantic import BaseModel, Field


# ─────────────────── hook ───────────────────

class RecallRequest(BaseModel):
    # ``source`` is required (0.9.0): the server uses it to pick the
    # right adapter for ``mint_session_id``. Without it we'd be guessing
    # — that was the 0.8.x bug where Codex hooks wrote a claude-code-
    # shaped session_id.
    source: str
    # Adapter location (filesystem path / URL). Defaults to the
    # adapter's ``DEFAULT_LOCATION`` when omitted; multi-endpoint users
    # must supply explicitly so loc_code matches sync.
    location: str | None = None
    # Raw upstream id (e.g. Claude Code UUID). Server mints canonical
    # via the supplied source/location.
    session_id: str
    prompt: str
    top_k: int | None = None  # falls back to settings.recall.default_top_k


class RecalledCard(BaseModel):
    card_id: str
    insight: str


class RecallResponse(BaseModel):
    session_id: str  # canonical: ``sess-<loc8>-<tail>``
    query: str
    recalled: list[RecalledCard] = Field(default_factory=list)
    # Card ids that *would* have matched but were already returned in
    # an earlier ``recall_event`` for this session — exposed so callers
    # can see what dedup filtered out.
    skipped_already_recalled: list[str] = Field(default_factory=list)


# ─────────────────── list ───────────────────

class RecallSessionSummary(BaseModel):
    session_id: str           # canonical
    recalls: int              # total recall_event rows for this session
    unique_cards: int         # DISTINCT card_ids across all returned_ids
    last_recall: str          # UTC ISO 8601 of most recent event


class RecallListResponse(BaseModel):
    sessions: list[RecallSessionSummary] = Field(default_factory=list)


# ─────────────────── read ───────────────────

class RecallEventOut(BaseModel):
    event_id: str
    ts: str
    prompt: str
    returned: list[RecalledCard] = Field(default_factory=list)
    skipped: list[RecalledCard] = Field(default_factory=list)


class RecallReadResponse(BaseModel):
    session_id: str
    events: list[RecallEventOut] = Field(default_factory=list)
