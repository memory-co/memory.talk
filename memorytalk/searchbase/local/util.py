"""Internal utilities for the local searchbase backend.

Everything in here was scattered before — column conventions sitting at
the top of ``backend.py`` AND ``index.py``, SQL string helpers split
across two files, text preparation in a third, a ``_utc_iso`` re-defined
every time someone needed a timestamp. This module is one place to look
for "what tiny tools does the local backend use?".

Organized by section below. Identifiers don't carry leading
underscores — being in ``searchbase/local/`` is already the "internal"
signal; doubling it on every name was redundant.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

import pyarrow as pa


# ── Column conventions ──────────────────────────────────────────────
#
# What columns the index machinery reserves for its own use (carried
# on every row but not part of the caller's Doc.fields). Three flavors:
# RESERVED = on-disk columns we own; SCORE = transient columns LanceDB
# returns from search; NON_DOC_FIELDS = what to exclude when projecting
# a row back into a Hit's fields dict.

RESERVED_COLUMNS = ("id", "text", "vector", "_base_id", "_chunk")
SCORE_COLUMNS = ("_score", "_distance", "_relevance_score")
NON_DOC_FIELDS = RESERVED_COLUMNS + SCORE_COLUMNS


# ── Declared field type tags → Arrow types ──────────────────────────
#
# Used by CollectionIndex._schema_for. Unknown tag → KeyError on
# schema construction, which is the right fail-fast: a typo in a
# declared collection schema is a code bug.

TYPE_TAGS: dict[str, pa.DataType] = {
    "str": pa.string(),
    "int": pa.int64(),
    "float": pa.float64(),
    "bool": pa.bool_(),
}


# ── Time ────────────────────────────────────────────────────────────

def utc_iso() -> str:
    """UTC now as ISO-8601 with the ``Z`` suffix.

    Canonical timestamp format across memory.talk's persistence
    surfaces (events.jsonl, SQLite ``*_at`` columns, log files).
    """
    return _dt.datetime.now(_dt.UTC).isoformat(
        timespec="seconds",
    ).replace("+00:00", "Z")


# ── SQL string builders ─────────────────────────────────────────────
#
# LanceDB SQL fragments built by hand because there's no parameter
# binding in the AsyncTable API. Keys come from declared schemas
# (validated at create) and values come from a fixed set of types, so
# the renderer doesn't have to defend against arbitrary input.

def sql_literal(value) -> str:
    """Render a field value as a LanceDB SQL literal — quote strings
    (escaping single quotes), leave numbers bare."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def in_clause(ids: list[str], column: str) -> Optional[str]:
    """Build a ``column IN ('a', 'b', ...)`` predicate; ``None`` when
    ``ids`` is empty (caller should skip the whole delete/update)."""
    if not ids:
        return None
    quoted = ", ".join("'" + i.replace("'", "''") + "'" for i in ids)
    return f"{column} IN ({quoted})"


def where_from_match(match: dict | None) -> str | None:
    """Generic field-equality filter. ``match`` keys are stored column
    names — the backend never interprets what they mean."""
    if not match:
        return None
    return " AND ".join(
        f"{k} = {sql_literal(v)}" for k, v in match.items()
    )


# ── Text preparation ────────────────────────────────────────────────

def segment(text: str) -> str:
    """jieba 预分词,空格连接(亚毫秒级,同步)。LanceDB FTS uses a
    whitespace tokenizer, so we pre-segment Chinese on the write side
    AND on query."""
    import jieba
    return " ".join(jieba.cut(text or ""))


def split_text(text: str, max_len: int) -> list[str]:
    """Fixed-size chunks of ``text`` (at most ``max_len`` chars each).
    Always returns at least one chunk."""
    text = text or ""
    if len(text) <= max_len:
        return [text]
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


def collapse_chunks(rows: list[dict]) -> list[dict]:
    """Collapse chunk rows of an auto_split collection back to one row
    per logical doc: group by ``_base_id``, keep the best-scoring chunk,
    and present its ``id`` as the logical (base) id. Chunking is thus
    invisible to the caller."""
    best: dict[str, dict] = {}
    for r in rows:
        base = r.get("_base_id") or r.get("id")
        score = float(r.get("_score", 0.0))
        if base not in best or score > float(best[base].get("_score", 0.0)):
            row = dict(r)
            row["id"] = base
            best[base] = row
    return sorted(
        best.values(),
        key=lambda r: float(r.get("_score", 0.0)),
        reverse=True,
    )


# ── Error classification ────────────────────────────────────────────

def is_emfile(exc: BaseException) -> bool:
    """Recognize Lance's wrapped EMFILE — comes through as a
    ``RuntimeError`` whose ``str()`` contains "Too many open files".
    We can't match on errno because Lance wraps the OS error inside
    its own ``LanceError(IO)`` before raising. String match is fragile
    but it's the only signal Lance gives us on this path."""
    msg = str(exc)
    return "Too many open files" in msg or "(os error 24)" in msg


# ── Hybrid query execution ──────────────────────────────────────────

async def run_hybrid(
    table, query: str, vector: list[float] | None,
    top_k: int, where: str | None,
) -> list[dict]:
    """Hybrid FTS + vector search with RRF reranking.

    Reranker history (read before changing — there's a trap here):

    - **RRFReranker(K=60)** (current). Rank-based fusion. Output scale
      is small (~0.033 top) and the rank-1-vs-rank-2 differential is
      tiny (~0.0003), so the absolute score doesn't reflect match
      strength. We compensate downstream:
        * ``service/search.py:_aggregate_session_relevance`` is ``max``
          (not noisy-OR — see its docstring for why noisy-OR was wrong);
        * ``ranking_formula`` only consumes RRF as one signal among
          stats / age.

    - **LinearCombinationReranker (tried 2026-05-23, reverted same day)**.
      Looked attractive because it nominally uses actual BM25 + vector
      scores. But in ``lancedb==0.30.x`` the implementation is
      **inverted and unnormalized**:
      ``combined = 1 - (0.7 * vec_sim + 0.3 * bm25_raw)`` where BM25
      is unbounded (~30+ for strong matches) and vec_sim is [0, 1].
      Higher BM25 → lower combined → after min-max normalization the
      perfect-match round lands near 0 and noisy "fill" rows land
      near 1. A perfect-text-match round vanished from top 1000 in
      production — see ``docs/report/2026-05-23-search-linear-combination-regression.md``
      for the evidence chain. Lance's own docstring carries a
      ``TODO: pretty confusing as we invert scores``.

    **Do not switch to LinearCombinationReranker without** (a) Lance
    upstream fixing the inversion + adding normalization, or (b)
    landing a search-quality regression test that asserts perfect
    text matches stay in top-k on a fixed corpus.
    """
    from lancedb.rerankers import RRFReranker

    q = table.query()
    has_vector = vector is not None and len(vector) > 0
    has_text = bool(query and query.strip())

    if has_vector:
        q = q.nearest_to(vector)
    if has_text:
        q = q.nearest_to_text(segment(query))
    if not has_vector and not has_text:
        # Pure scan — no relevance to compute, only useful when a `where`
        # filter narrows things. The reranker would crash without anchors.
        if where:
            q = q.where(where)
        q = q.limit(top_k)
        rows = await q.to_list()
        for r in rows:
            r["_score"] = 0.0
        return rows
    if has_vector and has_text:
        q = q.rerank(reranker=RRFReranker(K=60))
    if where:
        q = q.where(where)
    q = q.limit(top_k)
    rows = await q.to_list()
    # Normalize the score field: LanceDB returns it under different names
    # depending on mode (_distance / _relevance_score / _score). Project
    # to a single ``_score`` so the caller doesn't care.
    for r in rows:
        if "_score" in r:
            continue
        if "_relevance_score" in r:
            r["_score"] = float(r["_relevance_score"])
        elif "_distance" in r:
            # cosine distance in [0,2] → similarity in [-1,1]; map to [0,1].
            r["_score"] = max(0.0, 1.0 - float(r["_distance"]) / 2.0)
        else:
            r["_score"] = 0.0
    return rows
