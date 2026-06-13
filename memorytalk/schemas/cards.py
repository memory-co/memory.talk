"""POST /v3/cards — request + response.

These shapes are the **write-side** counterpart to ``schemas.card.Card``:

- ``CardRoundRef`` is a *reference* to rounds in a source session
  (``{session_id, indexes}``). The server expands it into the stored
  ``CardRound[]`` shape using the source session's actual rounds.
- ``CreateCardRequest`` accepts these references + an immutable insight +
  optional ``source_cards`` (card-to-card edges).
"""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, Field

from memorytalk.schemas.card import CardStats, SourceCard


class CardRoundRef(BaseModel):
    """One ``rounds[]`` entry on a card-create request — points at a slice
    of rounds inside a single session."""
    session_id: str
    # Free-form syntax: '11-15' / '3,7,12' / '4'. Parsing + validation
    # happen in the service layer so the error message can carry the
    # parser's own diagnostic.
    indexes: str


class CreateCardRequest(BaseModel):
    insight: str
    rounds: list[CardRoundRef] = Field(default_factory=list)
    source_cards: list[SourceCard] = Field(default_factory=list)
    # Optional pre-supplied id; auto-generated when missing. Must start
    # with the card prefix — checked in the service.
    card_id: str | None = None
    # 0.8.x: optional user-side tags. Validated identically to PATCH
    # /v3/cards/{cid}/tags; any violation rejects the whole create.
    tags: dict[str, str] = Field(default_factory=dict)
    # Optional explore association (advisory link, not a gate).
    explore_id: str | None = None


class CreateCardResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str


# ─── 0.8.x: list ───────────────────────────────────────────────────

class CardMeta(BaseModel):
    """One row in ``GET /v3/cards``.

    Carries the same fields as ``Card`` payload-side **plus** stats
    and tags, but **without** the expanded ``rounds`` array — list
    output is metadata-only (``read <cid>`` covers full content).
    """
    card_id: str
    insight: str
    created_at: str
    tags: dict[str, str] = Field(default_factory=dict)
    stats: CardStats = Field(default_factory=CardStats)


class CardListResponse(BaseModel):
    total: int
    returned: int
    cards: list[CardMeta] = Field(default_factory=list)


class CardDeleteResponse(BaseModel):
    """Response for ``DELETE /v3/cards/{card_id}``.

    ``reviews_deleted`` and ``inbound_refs_dangling`` give the caller
    enough information to surface the blast radius. We don't return a
    ``files_deleted`` / ``vector_deleted`` because those are
    best-effort cleanup; from the user's POV the card IS gone."""
    card_id: str
    reviews_deleted: int = 0
    # Number of OTHER cards that referenced this one via source_cards.
    # Those references now dangle (cards point at a missing card_id).
    # Not cascaded by design — see docs/structure/v3/talk-card.md.
    inbound_refs_dangling: int = 0


class CardTagResponse(BaseModel):
    """Response of ``PATCH /v3/cards/{cid}/tags`` — full post-merge
    tag dict. Mirrors :class:`TagResponse` in shape; we keep them as
    siblings rather than a shared class because the id field name
    (``card_id`` vs ``session_id``) is part of each endpoint's contract.
    """
    card_id: str
    tags: dict[str, str] = Field(default_factory=dict)
