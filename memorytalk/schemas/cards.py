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

from memorytalk.schemas.card import SourceCard


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


class CreateCardResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
