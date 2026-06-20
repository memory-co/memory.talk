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


class MarkInput(BaseModel):
    # ``id`` is explicit ``m<n>`` (not server-assigned). ``indexes`` is
    # required only when ``mark`` carries ``#…？``; the service validates.
    id: str
    mark: str
    indexes: str | None = None


class SubmitMarksRequest(BaseModel):
    last_index: int
    description: str
    marks: list[MarkInput]


class CreateCardResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str


class CreatePositionRequest(BaseModel):
    claim: str
    scope: str = ""
    source: SourceRef | None = None
    forked_from: str | None = None      # 'p<n>' | None (lineage)


class CreatePositionResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    position: str                       # card-scoped seq 'p<n>'


class CreateReviewRequest(BaseModel):
    # target is the addressed subordinate: ``card_id#p<n>`` or ``card_id#l<n>``.
    # The route already knows the card + seq, so target is optional on the
    # request body (path is authoritative).
    target: str | None = None
    session_id: str
    indexes: str
    argument: Literal[-1, 0, 1]
    comment: str | None = None
    review_id: str | None = None


class CreateReviewResponse(BaseModel):
    status: Literal["ok"] = "ok"
    review_id: str
    target: str                         # 'card_id#p<n>' | 'card_id#l<n>'
    target_kind: str                    # 'position' | 'link'
    argument: int


class CreateLinkRequest(BaseModel):
    type: Literal[
        "specializes", "suggested_by", "questions", "replaces", "related"
    ]
    target_id: str
    claim: str
    card_id: str | None = None


class CreateLinkResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    link: str                           # card-scoped seq 'l<n>'
    type: str
    target_id: str
    target_type: str
    claim: str


class CreateCardSessionRequest(BaseModel):
    session_id: str
    position: str = ""             # "" = card-level, else 'p<n>' provenance
    indexes: str = "[]"


class CreateCardSessionResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    session_id: str
    position: str


class V4SearchRequest(BaseModel):
    query: str = ""
    where: str | None = None
    limit: int = 20


class V4RecallRequest(BaseModel):
    session_id: str
    prompt: str
    top_k: int = 5
