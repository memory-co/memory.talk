"""v2 Pydantic schemas — API wire format.

Split by endpoint group to mirror api/ and service/. Shared types
(ContentBlock, SessionRound, CardRound, LinkRef) live in shared.py.
Handlers can import from the submodule or from this package root.
"""
from memorytalk.schemas.cards import (
    CardRoundsItem, CreateCardRequest, CreateCardResponse,
)
from memorytalk.schemas.links import CreateLinkRequest, CreateLinkResponse
from memorytalk.schemas.log import EventEntry, LogRequest, LogResponse
from memorytalk.schemas.rebuild import RebuildResponse
from memorytalk.schemas.search import (
    CardHit, SearchBucket, SearchRequest, SearchResponse, SessionHit,
)
from memorytalk.schemas.sessions import (
    IngestRound, IngestSessionRequest, IngestSessionResponse,
)
from memorytalk.schemas.shared import (
    CardRound, ContentBlock, LinkRef, LinkTargetType, ObjectKind, SessionRound,
)
from memorytalk.schemas.status import StatusResponse
from memorytalk.schemas.tags import TagsRequest, TagsResponse
from memorytalk.schemas.view import (
    CardView, SessionView, ViewRequest, ViewResponse,
)


__all__ = [
    # shared
    "LinkTargetType", "ObjectKind",
    "ContentBlock", "SessionRound", "CardRound", "LinkRef",
    # sessions
    "IngestRound", "IngestSessionRequest", "IngestSessionResponse",
    # cards
    "CardRoundsItem", "CreateCardRequest", "CreateCardResponse",
    # links
    "CreateLinkRequest", "CreateLinkResponse",
    # tags
    "TagsRequest", "TagsResponse",
    # search
    "SearchRequest", "CardHit", "SessionHit", "SearchBucket", "SearchResponse",
    # view
    "ViewRequest", "CardView", "SessionView", "ViewResponse",
    # log
    "LogRequest", "EventEntry", "LogResponse",
    # status
    "StatusResponse",
    # rebuild
    "RebuildResponse",
]
