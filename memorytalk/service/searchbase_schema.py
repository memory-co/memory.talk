"""Business → searchbase collection schemas.

searchbase is domain-agnostic; THIS module is where the business declares
what each vector collection holds. The id of a card row is its card_id;
the id of a round row is ``f"{session_id}:{idx}"`` (rounds carry
session_id/idx/role as fields so they can be filtered and displayed).

``INSTANCE_NAME`` versions the on-disk index. Bump it whenever a schema
here changes — a new name is a new directory that the (separate) upgrade
flow re-fills from the SQLite/jsonl source of truth; the old instance
keeps serving until the switch.
"""
from __future__ import annotations

CARDS = "cards"
ROUNDS = "rounds"

# Max text length searchbase will accept per doc. The business caps text
# to this before writing (searchbase rejects over-length writes rather
# than silently truncating). 2000 chars was the legacy embed cap.
MAX_TEXT_LENGTH = 2000


def cap_text(text: str | None) -> str:
    """Cap text to MAX_TEXT_LENGTH before handing it to searchbase."""
    return (text or "")[:MAX_TEXT_LENGTH]

SCHEMAS: dict[str, dict[str, str]] = {
    CARDS: {},
    ROUNDS: {"session_id": "str", "idx": "int", "role": "str"},
}

INSTANCE_NAME = "v1"


def round_doc_id(session_id: str, idx: int) -> str:
    """Stable unique id for a round row (the generic backend keys on a
    single ``id`` column; rounds' natural key is the (session, idx) pair)."""
    return f"{session_id}:{idx}"
