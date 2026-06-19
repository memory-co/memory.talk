"""Pydantic schemas — request / response shapes for the v3 HTTP API."""
from memorytalk.schemas.card import Card, CardStats, SourceCard, CardRound
from memorytalk.schemas.cards import (
    CardDeleteResponse, CardListResponse, CardMeta, CardRoundRef, CardTagResponse,
    CreateCardRequest, CreateCardResponse,
)
from memorytalk.schemas.read import ReadRequest, ReadResponse
from memorytalk.schemas.recall import (
    RecallEventOut,
    RecallListResponse,
    RecallReadResponse,
    RecallRequest,
    RecallResponse,
    RecallSessionSummary,
    RecalledCard,
)
from memorytalk.schemas.search import (
    CardResult, SearchRequest, SearchResponse, SessionHit, SessionResult,
)
from memorytalk.schemas.session import (
    AppendRoundsRequest, AppendRoundsResponse,
    ContentBlock, EnsureSessionRequest, EnsureSessionResponse,
    ReadAfterResult, Round, RoundInput, Session,
    SessionListResponse, SessionMeta, SourceProbe,
    TagPatchRequest, TagResponse,
)
from memorytalk.schemas.status import StatusResponse
from memorytalk.schemas.sync import (
    SyncStartResponse, SyncStatusResponse, SyncStopResponse,
)


__all__ = [
    "Card", "CardStats", "SourceCard", "CardRound",
    "CardDeleteResponse", "CardListResponse", "CardMeta", "CardRoundRef",
    "CardTagResponse",
    "CreateCardRequest", "CreateCardResponse",
    "ReadRequest", "ReadResponse",
    "RecalledCard", "RecallRequest", "RecallResponse",
    "RecallEventOut", "RecallListResponse", "RecallReadResponse", "RecallSessionSummary",
    "CardResult", "SearchRequest", "SearchResponse", "SessionHit", "SessionResult",
    "ContentBlock",
    "AppendRoundsRequest", "AppendRoundsResponse",
    "EnsureSessionRequest", "EnsureSessionResponse",
    "ReadAfterResult", "Round", "RoundInput", "Session",
    "SessionListResponse", "SessionMeta", "SourceProbe",
    "TagPatchRequest", "TagResponse",
    "StatusResponse",
    "SyncStartResponse", "SyncStatusResponse", "SyncStopResponse",
]
