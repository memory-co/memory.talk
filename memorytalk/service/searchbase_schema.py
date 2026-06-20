"""Business → searchbase collection schemas.

searchbase is domain-agnostic; THIS module is where the business declares
what each vector collection holds. The id of a card row is its card_id;
the id of a round row is ``f"{session_id}:{idx}"`` (rounds carry
session_id/idx/role as fields so they can be filtered and displayed).

Schema evolution (column adds, renames) is the
``memorytalk.migration`` framework's responsibility, NOT a build-time
concern here. The constants declared in this module describe the
**current** product schema; the migration framework's job is to bring
existing on-disk schemas up to match.
"""
from __future__ import annotations

INSIGHTS = "insights"
ROUNDS = "rounds"
# v4 card subsystem collections. ``cards`` embeds the Issue (question-level
# retrieval); ``positions`` embeds the Claim (answer-level retrieval) and
# carries ``card_id`` as a field so a position hit maps back to its card.
# The ``cards`` name was freed by the v3 card→insight rename.
V4_CARDS = "cards"
V4_POSITIONS = "positions"

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
    INSIGHTS: {"fields": {}},
    ROUNDS: {
        "fields": {"session_id": "str", "idx": "int", "role": "str"},
        "auto_split": True,
    },
    # v4: issue embedding (id = card_id, text = issue). Short like
    # insights → no auto_split, reject-and-skip on over-length.
    V4_CARDS: {"fields": {}},
    # v4: claim embedding (id = card_id#position address, text = claim).
    # card_id kept as a field so a position hit maps back to / groups by its
    # card.
    V4_POSITIONS: {"fields": {"card_id": "str"}},
}


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
        # name="" (default) → flat layout under data_dir/, matching
        # 0.8.x. Schema evolution happens in-place via the migration
        # framework (memorytalk/migration/), not by switching directories.
        data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim,
        embedder=get_embedder(config),
        collections=SCHEMAS,
        max_text_length=MAX_TEXT_LENGTH,
        # Per-category file logs under logs/searchbase/.
        # searchbase itself just gets a Path — no Config awareness.
        log_dir=config.searchbase_log_dir,
    )
