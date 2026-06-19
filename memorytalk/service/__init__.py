"""Service layer — orchestrates repository + provider; one class per noun."""
from memorytalk.service.insights import (
    InsightConflict, InsightNotFound, InsightServiceError,
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
    "InsightServiceError", "InsightConflict",
    "RecallService", "RecallServiceError",
]
