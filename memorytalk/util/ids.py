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
INSIGHT_PREFIX = "insight_"       # v4/insight (renamed v3 card; read-only)
SESSION_PREFIX = "sess-"          # canonical (new, 0.7.x)
SESSION_PREFIX_LEGACY = "sess_"   # accepted on read for older data
REVIEW_PREFIX = "review_"
EXPLORE_PREFIX = "explore_"
SEARCH_PREFIX = "sch_"
EVENT_PREFIX = "evt_"

# Card-scoped / session-scoped subordinate-id markers. These objects have
# NO global prefixed id -- they are addressed by a fragment on their parent:
# Position = ``<card_id>#p<n>``, CardLink = ``<card_id>#l<n>``,
# SessionMark = ``<session_id>#m<n>``.
FRAGMENT_SEP = "#"
POSITION_SEQ_PREFIX = "p"
LINK_SEQ_PREFIX = "l"
MARK_SEQ_PREFIX = "m"


class IdKind(str, Enum):
    CARD = "card"
    INSIGHT = "insight"
    SESSION = "session"
    REVIEW = "review"
    SEARCH = "search"
    EVENT = "event"
    # fragment kinds (subordinate ids, no global prefix)
    POSITION = "position"
    LINK = "link"
    MARK = "mark"


class InvalidIdError(ValueError):
    """Raised when an id string does not match any known v3 prefix."""


def new_card_id() -> str:
    return f"{CARD_PREFIX}{ULID()}"


def new_insight_id() -> str:
    return f"{INSIGHT_PREFIX}{ULID()}"


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
        (INSIGHT_PREFIX, IdKind.INSIGHT),
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


# -- card-scoped / session-scoped subordinate-id helpers --

def position_seq(n: int) -> str:
    """Format a card-scoped Position seq: ``3`` -> ``'p3'``."""
    return f"{POSITION_SEQ_PREFIX}{n}"


def link_seq(n: int) -> str:
    """Format a card-scoped CardLink seq: ``2`` -> ``'l2'``."""
    return f"{LINK_SEQ_PREFIX}{n}"


def mark_seq(n: int) -> str:
    """Format a session-scoped SessionMark seq: ``1`` -> ``'m1'``."""
    return f"{MARK_SEQ_PREFIX}{n}"


# fragment-prefix -> (kind, parent expectation) for parse_fragment
_FRAGMENT_KINDS = {
    POSITION_SEQ_PREFIX: IdKind.POSITION,
    LINK_SEQ_PREFIX: IdKind.LINK,
    MARK_SEQ_PREFIX: IdKind.MARK,
}


def parse_fragment(id_str: str) -> tuple[str, IdKind, str]:
    """Parse a fragment-addressed subordinate id ``<base_id>#<seq>``.

    ``card_…#p3``  -> ``(card_id, IdKind.POSITION, 'p3')``
    ``card_…#l2``  -> ``(card_id, IdKind.LINK,     'l2')``
    ``sess…#m1``   -> ``(session_id, IdKind.MARK,  'm1')``

    Ids without ``#`` fall through to :func:`parse_id` and are returned as
    ``(id_str, kind, id_str)`` so callers can branch on ``IdKind``. Raises
    ``InvalidIdError`` on an unrecognised fragment seq prefix.
    """
    if FRAGMENT_SEP not in id_str:
        kind, _ = parse_id(id_str)
        return id_str, kind, id_str
    base_id, _, seq = id_str.partition(FRAGMENT_SEP)
    if not seq:
        raise InvalidIdError(f"empty fragment seq: {id_str!r}")
    kind = _FRAGMENT_KINDS.get(seq[0])
    if kind is None or not seq[1:].isdigit():
        raise InvalidIdError(f"unknown fragment seq: {id_str!r}")
    return base_id, kind, seq
