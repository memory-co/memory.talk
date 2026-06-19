"""Pydantic schemas — request / response shapes for the v3 HTTP API."""
from memorytalk.schemas.insight import Insight, InsightStats, SourceInsight, InsightRound
from memorytalk.schemas.insights import (
    InsightDeleteResponse, InsightListResponse, InsightMeta, CardRoundRef, InsightTagResponse,
    CreateInsightRequest, CreateInsightResponse,
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
    "Insight", "InsightStats", "SourceInsight", "InsightRound",
    "InsightDeleteResponse", "InsightListResponse", "InsightMeta", "CardRoundRef",
    "InsightTagResponse",
    "CreateInsightRequest", "CreateInsightResponse",
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
