"""v4 write request/response models (API + service boundary)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SourceRef(BaseModel):
    session_id: str
    indexes: str


class CreateCardRequest(BaseModel):
    issue: str
    card_id: str | None = None


class CreateCardResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str


class CreatePositionRequest(BaseModel):
    claim: str
    scope: str = ""
    source: SourceRef | None = None
    forked_from_position_id: str | None = None
    position_id: str | None = None


class CreatePositionResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    position_id: str


class CreateReviewRequest(BaseModel):
    position_id: str
    session_id: str
    indexes: str
    argument: Literal[-1, 0, 1]
    comment: str | None = None
    review_id: str | None = None


class CreateReviewResponse(BaseModel):
    status: Literal["ok"] = "ok"
    review_id: str
    position_id: str
    argument: int


class CreateLinkRequest(BaseModel):
    card_id: str
    type: Literal[
        "specializes", "suggested_by", "questions", "replaces", "related"
    ]
    target_id: str


class CreateLinkResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    type: str
    target_id: str
    target_type: str


class CreateCardSessionRequest(BaseModel):
    session_id: str
    position_id: str = ""          # "" = card-level association
    indexes: str = "[]"


class CreateCardSessionResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    session_id: str
    position_id: str


class V4SearchRequest(BaseModel):
    query: str = ""
    where: str | None = None
    limit: int = 20


class V4RecallRequest(BaseModel):
    session_id: str
    prompt: str
    top_k: int = 5
