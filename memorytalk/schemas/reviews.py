"""POST /v3/reviews — request + response."""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel


class CreateReviewRequest(BaseModel):
    card_id: str
    session_id: str
    # Same syntax as card rounds.indexes — "20-25" / "3,7,12" / "4".
    # Parsed and range-checked in the service.
    indexes: str
    # Stance: 1 endorses / 0 neutral (annotation only) / -1 refutes.
    # pydantic Literal yields a 422 on invalid input; the docs spec'd 400
    # so the service layer also validates and raises a 400-shaped error
    # for parity with the rest of the v3 API.
    score: Literal[-1, 0, 1]
    comment: str | None = None
    # Optional explore association (advisory link, not a gate).
    explore_id: str | None = None
    review_id: str | None = None


class CreateReviewResponse(BaseModel):
    status: Literal["ok"] = "ok"
    review_id: str
    card_id: str
    session_id: str
    score: int
