"""v2 ID utilities — prefix-based typed identifiers."""
from __future__ import annotations
from enum import Enum
from ulid import ULID


CARD_PREFIX = "card_"
SESSION_PREFIX = "sess_"
LINK_PREFIX = "link_"


class IdKind(str, Enum):
    CARD = "card"
    SESSION = "session"
    LINK = "link"


class InvalidIdError(ValueError):
    """Raised when an id string does not match any v2 prefix."""


def new_card_id() -> str:
    return f"{CARD_PREFIX}{ULID()}"


def new_link_id() -> str:
    return f"{LINK_PREFIX}{ULID()}"


def new_session_id() -> str:
    """Mint a brand-new session id with a freshly-generated ULID payload.
    Most v2 sessions originate from sync — use prefix_session_id() with the
    platform's existing id. This helper is for synthetic / test sessions."""
    return f"{SESSION_PREFIX}{ULID()}"


def prefix_session_id(platform_id: str) -> str:
    """Prefix a raw platform session id with `sess_`. Idempotent."""
    if platform_id.startswith(SESSION_PREFIX):
        return platform_id
    return f"{SESSION_PREFIX}{platform_id}"


def parse_id(id_str: str) -> tuple[IdKind, str]:
    """Parse a prefixed id into (kind, raw_id). Raises InvalidIdError if no known prefix."""
    if id_str.startswith(CARD_PREFIX):
        return IdKind.CARD, id_str[len(CARD_PREFIX):]
    if id_str.startswith(SESSION_PREFIX):
        return IdKind.SESSION, id_str[len(SESSION_PREFIX):]
    if id_str.startswith(LINK_PREFIX):
        return IdKind.LINK, id_str[len(LINK_PREFIX):]
    raise InvalidIdError(f"id must start with {CARD_PREFIX!r}, {SESSION_PREFIX!r}, or {LINK_PREFIX!r}: got {id_str!r}")
