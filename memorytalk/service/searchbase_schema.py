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

# Max text length searchbase will accept per doc (passed in at
# construction; searchbase itself never reads settings). Over-length
# writes are rejected. 2000 chars was the legacy embed cap.
# TODO(setup-sense): detect the embedding endpoint's real max input
# length during `memory.talk setup` (local: model.max_seq_length;
# openai/dashscope: known-model table + conservative fallback) and
# persist it in settings instead of this hardcoded constant.
MAX_TEXT_LENGTH = 2000


def cap_text(text: str | None) -> str:
    """Cap text to MAX_TEXT_LENGTH before handing it to searchbase."""
    return (text or "")[:MAX_TEXT_LENGTH]

# Each collection: ``{"fields": {field: type_tag}, "auto_split": bool}``.
# Rounds enable auto_split — a single long conversation turn is chunked
# across multiple rows by searchbase (invisible on read) instead of being
# rejected. Cards don't: insights are short, and a rejected card just
# stays un-indexed (no backfill loop), so reject-and-skip is fine.
SCHEMAS: dict[str, dict] = {
    CARDS: {"fields": {}},
    ROUNDS: {
        "fields": {"session_id": "str", "idx": "int", "role": "str"},
        "auto_split": True,
    },
}

INSTANCE_NAME = "v1"


def round_doc_id(session_id: str, idx: int) -> str:
    """Stable unique id for a round row (the generic backend keys on a
    single ``id`` column; rounds' natural key is the (session, idx) pair)."""
    return f"{session_id}:{idx}"


async def build_search_backend(config):
    """Map ``config.settings`` → a searchbase instance. This is the ONLY
    place that reads config for searchbase; searchbase itself takes plain
    values and is config-agnostic. Also the seam where a future
    local/server choice would be made off config."""
    from memorytalk.provider.embedding import get_embedder
    from memorytalk.searchbase import LocalSearchBackend

    return await LocalSearchBackend.create(
        name=INSTANCE_NAME,
        data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim,
        embedder=get_embedder(config),
        collections=SCHEMAS,
        max_text_length=MAX_TEXT_LENGTH,
    )
