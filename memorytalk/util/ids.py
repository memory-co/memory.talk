"""Prefixed typed identifiers.

v3 objects have type-prefixed ids so routing (e.g. ``/v3/read``) can
dispatch by prefix with zero lookup cost. A raw platform session id gets
prefixed exactly once at the ingest boundary via ``prefix_session_id``.
"""
from __future__ import annotations
from enum import Enum
from ulid import ULID


CARD_PREFIX = "card_"
SESSION_PREFIX = "sess_"
REVIEW_PREFIX = "review_"
SEARCH_PREFIX = "sch_"
EVENT_PREFIX = "evt_"


class IdKind(str, Enum):
    CARD = "card"
    SESSION = "session"
    REVIEW = "review"
    SEARCH = "search"
    EVENT = "event"


class InvalidIdError(ValueError):
    """Raised when an id string does not match any known v3 prefix."""


def new_card_id() -> str:
    return f"{CARD_PREFIX}{ULID()}"


def new_review_id() -> str:
    return f"{REVIEW_PREFIX}{ULID()}"


def new_search_id() -> str:
    return f"{SEARCH_PREFIX}{ULID()}"


def new_event_id() -> str:
    return f"{EVENT_PREFIX}{ULID()}"


def prefix_session_id(platform_id: str) -> str:
    """Prefix a raw platform session id with ``sess_``. Idempotent."""
    if platform_id.startswith(SESSION_PREFIX):
        return platform_id
    return f"{SESSION_PREFIX}{platform_id}"


def parse_id(id_str: str) -> tuple[IdKind, str]:
    """Parse a prefixed id into (kind, raw). Raises ``InvalidIdError`` on unknown prefix."""
    for prefix, kind in (
        (CARD_PREFIX, IdKind.CARD),
        (SESSION_PREFIX, IdKind.SESSION),
        (REVIEW_PREFIX, IdKind.REVIEW),
        (SEARCH_PREFIX, IdKind.SEARCH),
        (EVENT_PREFIX, IdKind.EVENT),
    ):
        if id_str.startswith(prefix):
            return kind, id_str[len(prefix):]
    raise InvalidIdError(f"unknown id prefix: {id_str!r}")
