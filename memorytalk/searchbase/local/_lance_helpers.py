"""Pure LanceDB query/segmentation helpers, extracted verbatim from the
legacy provider/lancedb.py so CollectionIndex no longer depends on it.

- ``_segment``    jieba pre-tokenization for FTS.
- ``_is_emfile``  recognize Lance's wrapped EMFILE.
- ``_in_clause``  build a SQL ``IN`` predicate.
- ``_run_hybrid`` hybrid FTS+vector search with RRF reranking (read the
  docstring before touching the reranker — there is a trap).
"""
from __future__ import annotations

from typing import Optional


def _is_emfile(exc: BaseException) -> bool:
    """Recognize Lance's wrapped EMFILE — comes through as a
    ``RuntimeError`` whose ``str()`` contains "Too many open files".
    We can't match on errno because Lance wraps the OS error inside
    its own ``LanceError(IO)`` before raising. String match is fragile
    but it's the only signal Lance gives us on this path."""
    msg = str(exc)
    return "Too many open files" in msg or "(os error 24)" in msg


def _segment(text: str) -> str:
    """jieba 预分词,空格连接(jieba.cut 同步,亚毫秒级)。"""
    import jieba
    return " ".join(jieba.cut(text or ""))


def _in_clause(ids: list[str], column: str) -> Optional[str]:
    if not ids:
        return None
    quoted = ", ".join("'" + i.replace("'", "''") + "'" for i in ids)
    return f"{column} IN ({quoted})"


async def _run_hybrid(
    table, query: str, vector: list[float] | None,
    top_k: int, where: str | None,
) -> list[dict]:
    """Internal: hybrid FTS + vector with RRF reranking.

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
      for the evidence chain. Lance's
      own docstring carries a ``TODO: pretty confusing as we invert
      scores``.

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
        q = q.nearest_to_text(_segment(query))
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
