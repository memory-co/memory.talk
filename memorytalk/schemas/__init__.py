"""Pydantic schemas — request / response shapes for the v3 HTTP API."""
from memorytalk.schemas.card import Card, CardStats, SourceCard, CardRound
from memorytalk.schemas.cards import (
    CardRoundRef, CreateCardRequest, CreateCardResponse,
)
from memorytalk.schemas.read import ReadRequest, ReadResponse
from memorytalk.schemas.recall import RecalledCard, RecallRequest, RecallResponse
from memorytalk.schemas.review import Review
from memorytalk.schemas.reviews import CreateReviewRequest, CreateReviewResponse
from memorytalk.schemas.search import (
    CardResult, SearchRequest, SearchResponse, SessionHit, SessionResult,
)
from memorytalk.schemas.session import (
    AppendRoundsRequest, AppendRoundsResponse,
    ContentBlock, EnsureSessionRequest, EnsureSessionResponse,
    IngestSessionRequest, IngestSessionResponse,
    ReadAfterResult, Round, RoundInput, Session, SourceProbe,
)
from memorytalk.schemas.status import StatusResponse
from memorytalk.schemas.sync import (
    SyncStartResponse, SyncStatusResponse, SyncStopResponse,
)


__all__ = [
    "Card", "CardStats", "SourceCard", "CardRound",
    "CardRoundRef", "CreateCardRequest", "CreateCardResponse",
    "ReadRequest", "ReadResponse",
    "RecalledCard", "RecallRequest", "RecallResponse",
    "Review", "CreateReviewRequest", "CreateReviewResponse",
    "CardResult", "SearchRequest", "SearchResponse", "SessionHit", "SessionResult",
    "ContentBlock",
    "AppendRoundsRequest", "AppendRoundsResponse",
    "EnsureSessionRequest", "EnsureSessionResponse",
    "IngestSessionRequest", "IngestSessionResponse",
    "ReadAfterResult", "Round", "RoundInput", "Session", "SourceProbe",
    "StatusResponse",
    "SyncStartResponse", "SyncStatusResponse", "SyncStopResponse",
]
