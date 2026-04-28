"""v2 Pydantic schemas — API wire format.

Split by endpoint group to mirror api/ and service/. Shared types
(ContentBlock, SessionRound, CardRound, LinkRef) live in shared.py.
Handlers can import from the submodule or from this package root.
"""
from memory_talk_v2.schemas.cards import (
    CardRoundsItem, CreateCardRequest, CreateCardResponse,
)
from memory_talk_v2.schemas.links import CreateLinkRequest, CreateLinkResponse
from memory_talk_v2.schemas.log import EventEntry, LogRequest, LogResponse
from memory_talk_v2.schemas.rebuild import RebuildResponse
from memory_talk_v2.schemas.search import (
    CardHit, SearchBucket, SearchRequest, SearchResponse, SessionHit,
)
from memory_talk_v2.schemas.sessions import (
    IngestRound, IngestSessionRequest, IngestSessionResponse,
)
from memory_talk_v2.schemas.shared import (
    CardRound, ContentBlock, LinkRef, LinkTargetType, ObjectKind, SessionRound,
)
from memory_talk_v2.schemas.status import StatusResponse
from memory_talk_v2.schemas.tags import TagsRequest, TagsResponse
from memory_talk_v2.schemas.view import (
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
