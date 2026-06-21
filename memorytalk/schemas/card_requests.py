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
    # ``id`` is explicit ``m<n>`` (not server-assigned). ``indexes`` is now
    # REQUIRED on every mark — it's what the ≥90% round-coverage check counts
    # (以写代读: a submission must read the whole session). ``mark`` (the text)
    # is OPTIONAL: an entry with no/empty ``mark`` is an id-only "read this
    # round(s), nothing to note" marker that still counts toward coverage via
    # its ``indexes`` but creates no #…？ issues / cards. The service validates.
    id: str
    indexes: str
    mark: str | None = None


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
    # Provenance: each (session_id, indexes) lands one position_sessions row
    # (position→session, position=p<n>). ``source`` is the single-source
    # convenience; ``sources`` carries a multi-source list. The service
    # unions both (see ``CreatePositionRequest.all_sources``).
    source: SourceRef | None = None
    sources: list[SourceRef] = []
    forked_from: str | None = None      # 'p<n>' | None (lineage)

    def all_sources(self) -> list[SourceRef]:
        """Union of ``source`` (single) + ``sources`` (list), in order."""
        out: list[SourceRef] = []
        if self.source is not None:
            out.append(self.source)
        out.extend(self.sources)
        return out


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
    # Provenance: each (session_id, indexes) lands one link_sessions row
    # (link→session, link=l<n>). Mirrors a Position's ``--source``.
    source: list[SourceRef] = []


class CreateLinkResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    link: str                           # card-scoped seq 'l<n>'
    type: str
    target_id: str
    target_type: str
    claim: str


class V4SearchRequest(BaseModel):
    query: str = ""
    where: str | None = None
    limit: int = 20


class V4RecallRequest(BaseModel):
    session_id: str
    prompt: str
    top_k: int = 5
