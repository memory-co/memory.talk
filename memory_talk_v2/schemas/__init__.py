"""v2 Pydantic schemas — API wire format.

Split by endpoint group to mirror api/ and service/. Shared types
(ContentBlock, SessionRound, CardRound, LinkRef) live in shared.py.
Handlers can import from the submodule or from this package root.
"""
from memory_talk_v2.schemas.cards import (
    CardRoundsItemIn, CreateCardIn, CreateCardOut,
)
from memory_talk_v2.schemas.links import CreateLinkIn, CreateLinkOut
from memory_talk_v2.schemas.log import EventEntry, LogIn, LogOut
from memory_talk_v2.schemas.rebuild import RebuildOut
from memory_talk_v2.schemas.search import (
    CardHit, SearchBucket, SearchIn, SearchOut, SessionHit,
)
from memory_talk_v2.schemas.sessions import (
    IngestRoundIn, IngestSessionIn, IngestSessionOut,
)
from memory_talk_v2.schemas.shared import (
    CardRound, ContentBlock, LinkRef, LinkTargetType, ObjectKind, SessionRound,
)
from memory_talk_v2.schemas.status import StatusOut
from memory_talk_v2.schemas.tags import TagsIn, TagsOut
from memory_talk_v2.schemas.view import (
    CardView, SessionView, ViewIn, ViewOut,
)


__all__ = [
    # shared
    "LinkTargetType", "ObjectKind",
    "ContentBlock", "SessionRound", "CardRound", "LinkRef",
    # sessions
    "IngestRoundIn", "IngestSessionIn", "IngestSessionOut",
    # cards
    "CardRoundsItemIn", "CreateCardIn", "CreateCardOut",
    # links
    "CreateLinkIn", "CreateLinkOut",
    # tags
    "TagsIn", "TagsOut",
    # search
    "SearchIn", "CardHit", "SessionHit", "SearchBucket", "SearchOut",
    # view
    "ViewIn", "CardView", "SessionView", "ViewOut",
    # log
    "LogIn", "EventEntry", "LogOut",
    # status
    "StatusOut",
    # rebuild
    "RebuildOut",
]
