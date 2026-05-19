"""Service layer — orchestrates repository + provider; one class per noun."""
from memorytalk.service.cards import (
    CardConflict, CardService, CardServiceError,
)
from memorytalk.service.events import EventWriter
from memorytalk.service.read import (
    CardNotFound, ReadService, SessionNotFound, ReadServiceError,
)
from memorytalk.service.recall import RecallService, RecallServiceError
from memorytalk.service.reviews import (
    ReviewConflict, ReviewService, ReviewServiceError,
)
from memorytalk.service.sessions import IngestService, IngestServiceError


__all__ = [
    "EventWriter",
    "ReadService", "ReadServiceError", "CardNotFound", "SessionNotFound",
    "IngestService", "IngestServiceError",
    "CardService", "CardServiceError", "CardConflict",
    "ReviewService", "ReviewServiceError", "ReviewConflict",
    "RecallService", "RecallServiceError",
]
