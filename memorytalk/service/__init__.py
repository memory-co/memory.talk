"""Service layer — orchestrates repository + provider; one class per noun."""
from memorytalk.service.insights import (
    InsightConflict, InsightNotFound, InsightService, InsightServiceError,
)
from memorytalk.service.events import EventWriter
from memorytalk.service.read import (
    ReadService, SessionNotFound, ReadServiceError,
)
from memorytalk.service.recall import RecallService, RecallServiceError
from memorytalk.service.sessions import IngestService, IngestServiceError


__all__ = [
    "EventWriter",
    "ReadService", "ReadServiceError", "InsightNotFound", "SessionNotFound",
    "IngestService", "IngestServiceError",
    "InsightService", "InsightServiceError", "InsightConflict",
    "RecallService", "RecallServiceError",
]
