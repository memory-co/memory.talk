"""Prefixed typed identifiers.

v3 objects have type-prefixed ids so routing (e.g. ``/v3/read``) can
dispatch by prefix with zero lookup cost.

session_id format
=================
Canonical: ``sess-<loc8>-<lastseg>`` where ``loc8`` is an 8-hex
sha256 of ``<source>#<location>`` and ``lastseg`` is the chunk after
the final ``-`` in the upstream raw id. Minted by adapters via
``BaseAdapter.mint_session_id``.

The 0.7.x rewrite dropped the older ``sess_<full-uuid>`` format. Both
``sess-`` and ``sess_`` are still recognized by ``parse_id`` (so a
half-migrated install doesn't crash on read), but new minting always
produces ``sess-``.
"""
from __future__ import annotations
from enum import Enum
from ulid import ULID


CARD_PREFIX = "card_"
SESSION_PREFIX = "sess-"          # canonical (new, 0.7.x)
SESSION_PREFIX_LEGACY = "sess_"   # accepted on read for older data
REVIEW_PREFIX = "review_"
EXPLORE_PREFIX = "explore_"
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


def new_explore_id() -> str:
    return f"{EXPLORE_PREFIX}{ULID()}"


def new_search_id() -> str:
    return f"{SEARCH_PREFIX}{ULID()}"


def new_event_id() -> str:
    return f"{EVENT_PREFIX}{ULID()}"


def parse_id(id_str: str) -> tuple[IdKind, str]:
    """Parse a prefixed id into (kind, raw). Raises ``InvalidIdError`` on unknown prefix."""
    for prefix, kind in (
        (CARD_PREFIX, IdKind.CARD),
        (SESSION_PREFIX, IdKind.SESSION),
        (SESSION_PREFIX_LEGACY, IdKind.SESSION),
        (REVIEW_PREFIX, IdKind.REVIEW),
        (SEARCH_PREFIX, IdKind.SEARCH),
        (EVENT_PREFIX, IdKind.EVENT),
    ):
        if id_str.startswith(prefix):
            return kind, id_str[len(prefix):]
    raise InvalidIdError(f"unknown id prefix: {id_str!r}")
