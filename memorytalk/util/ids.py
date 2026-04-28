"""Prefixed typed identifiers.

v2 objects have type-prefixed ids so routing (e.g. `/v2/view`) can dispatch
by prefix with zero lookup cost. A raw platform session id gets prefixed
exactly once at the ingest boundary via `prefix_session_id`.
"""
from __future__ import annotations
from enum import Enum
from ulid import ULID


CARD_PREFIX = "card_"
SESSION_PREFIX = "sess_"
LINK_PREFIX = "link_"
SEARCH_PREFIX = "sch_"
EVENT_PREFIX = "evt_"


class IdKind(str, Enum):
    CARD = "card"
    SESSION = "session"
    LINK = "link"
    SEARCH = "search"
    EVENT = "event"


class InvalidIdError(ValueError):
    """Raised when an id string does not match any known v2 prefix."""


def new_card_id() -> str:
    return f"{CARD_PREFIX}{ULID()}"


def new_link_id() -> str:
    return f"{LINK_PREFIX}{ULID()}"


def new_search_id() -> str:
    return f"{SEARCH_PREFIX}{ULID()}"


def new_event_id() -> str:
    return f"{EVENT_PREFIX}{ULID()}"


def prefix_session_id(platform_id: str) -> str:
    """Prefix a raw platform session id with `sess_`. Idempotent."""
    if platform_id.startswith(SESSION_PREFIX):
        return platform_id
    return f"{SESSION_PREFIX}{platform_id}"


def parse_id(id_str: str) -> tuple[IdKind, str]:
    """Parse a prefixed id into (kind, raw). Raises InvalidIdError on unknown prefix."""
    if id_str.startswith(CARD_PREFIX):
        return IdKind.CARD, id_str[len(CARD_PREFIX):]
    if id_str.startswith(SESSION_PREFIX):
        return IdKind.SESSION, id_str[len(SESSION_PREFIX):]
    if id_str.startswith(LINK_PREFIX):
        return IdKind.LINK, id_str[len(LINK_PREFIX):]
    if id_str.startswith(SEARCH_PREFIX):
        return IdKind.SEARCH, id_str[len(SEARCH_PREFIX):]
    if id_str.startswith(EVENT_PREFIX):
        return IdKind.EVENT, id_str[len(EVENT_PREFIX):]
    raise InvalidIdError(f"unknown id prefix: {id_str!r}")
