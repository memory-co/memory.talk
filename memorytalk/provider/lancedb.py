"""Async LanceDB store for the v3 search backend.

Two tables, both indexed for FTS and vector queries:

- ``cards``  — one row per card.   ``{card_id, text, vector}``
- ``rounds`` — one row per round.  ``{session_id, idx, role, text, vector}``

This is the v3 search source of truth — search.md's per-round recall maps
directly onto rows of the ``rounds`` table, and the card-level ad slots
in search results come from the ``cards`` table. SQLite holds zero search
state; jsonl files hold zero search state.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import pyarrow as pa


def _segment(text: str) -> str:
    """jieba 预分词,空格连接(jieba.cut 同步,亚毫秒级)。"""
    import jieba
    return " ".join(jieba.cut(text or ""))


def _in_clause(ids: list[str], column: str) -> Optional[str]:
    if not ids:
        return None
    quoted = ", ".join("'" + i.replace("'", "''") + "'" for i in ids)
    return f"{column} IN ({quoted})"


class LanceStore:
    CARDS = "cards"
    ROUNDS = "rounds"

    def __init__(self, db, data_dir: Path, dim: int):
        self.db = db
        self.data_dir = data_dir
        self.dim = dim
        self._cards_schema = pa.schema([
            pa.field("card_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ])
        # One row per round. ``idx`` is the session-internal index; pair
        # ``(session_id, idx)`` uniquely identifies a round.
        self._rounds_schema = pa.schema([
            pa.field("session_id", pa.string()),
            pa.field("idx", pa.int32()),
            pa.field("role", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ])

    @classmethod
    async def create(cls, data_dir: Path, dim: int = 384) -> "LanceStore":
        import lancedb
        db = await lancedb.connect_async(str(data_dir))
        return cls(db, Path(data_dir), dim)

    async def _exists(self, name: str) -> bool:
        result = await self.db.list_tables()
        return name in (result.tables if hasattr(result, "tables") else result)

    async def _get_or_create_cards(self):
        if await self._exists(self.CARDS):
            return await self.db.open_table(self.CARDS)
        return await self.db.create_table(self.CARDS, schema=self._cards_schema)

    async def _get_or_create_rounds(self):
        if await self._exists(self.ROUNDS):
            return await self.db.open_table(self.ROUNDS)
        return await self.db.create_table(self.ROUNDS, schema=self._rounds_schema)

    # ────────── cards ──────────

    async def add_card(self, card_id: str, text: str, embedding: list[float]) -> None:
        table = await self._get_or_create_cards()
        await table.delete(f"card_id = '{card_id}'")
        await table.add([{"card_id": card_id, "text": _segment(text), "vector": embedding}])

    async def delete_cards(self, card_ids: list[str]) -> None:
        if not await self._exists(self.CARDS) or not card_ids:
            return
        table = await self.db.open_table(self.CARDS)
        expr = " OR ".join(f"card_id = '{cid}'" for cid in card_ids)
        await table.delete(expr)

    # ────────── rounds ──────────

    async def add_rounds(self, rows: list[dict]) -> None:
        """Bulk insert per-round rows.

        Each row: ``{session_id, idx, role, text, vector}`` where ``text``
        is already segmented (caller's responsibility — typically via
        ``_segment``) and ``vector`` is a list[float] of length ``dim``.

        Idempotent on (session_id, idx): callers should ``delete_rounds``
        first if they want to replace existing rows. The default ingest
        path doesn't replace existing rounds (v3 is append-only), so this
        is just ``add``.
        """
        if not rows:
            return
        table = await self._get_or_create_rounds()
        await table.add(rows)

    async def delete_session_rounds(self, session_id: str) -> None:
        if not await self._exists(self.ROUNDS):
            return
        table = await self.db.open_table(self.ROUNDS)
        await table.delete(f"session_id = '{session_id}'")

    # ────────── FTS index maintenance ──────────

    async def ensure_fts_index(self, table_name: str) -> None:
        """Create the FTS index on the ``text`` column if absent.

        LanceDB's hybrid search needs an FTS index on the text column.
        Calling this once before queries is enough (the index is shared
        across queries; LanceDB picks up new rows automatically). Cheap
        no-op when the index already exists.
        """
        if not await self._exists(table_name):
            return
        from lancedb.index import FTS
        table = await self.db.open_table(table_name)
        try:
            indices = await table.list_indices()
            for idx in indices:
                cols = getattr(idx, "columns", None) or []
                if "text" in cols:
                    return  # already indexed
        except Exception:
            pass  # treat as "no index" and create one
        # whitespace tokenizer because ingest already segments via jieba.
        await table.create_index(
            "text", config=FTS(base_tokenizer="whitespace", with_position=True),
            replace=True,
        )

    # ────────── search ──────────

    async def search_cards(
        self,
        query: str,
        vector: list[float] | None,
        top_k: int,
        where: str | None = None,
    ) -> list[dict]:
        """Hybrid FTS+vector search on the cards table.

        Returns a list of ``{card_id, _score}`` rows (LanceDB also returns
        text/vector but callers usually just need card_id + relevance).
        Empty query → vector-only; no query and no vector → empty result.
        """
        if not await self._exists(self.CARDS):
            return []
        table = await self.db.open_table(self.CARDS)
        return await _run_hybrid(table, query, vector, top_k, where)

    async def search_rounds(
        self,
        query: str,
        vector: list[float] | None,
        top_k: int,
        where: str | None = None,
    ) -> list[dict]:
        """Hybrid FTS+vector search on the rounds table.

        Returns ``{session_id, idx, role, text, _score}`` rows. Caller is
        responsible for aggregating per session, dereffing the text from
        jsonl for display, etc.
        """
        if not await self._exists(self.ROUNDS):
            return []
        table = await self.db.open_table(self.ROUNDS)
        return await _run_hybrid(table, query, vector, top_k, where)


async def _run_hybrid(
    table, query: str, vector: list[float] | None,
    top_k: int, where: str | None,
) -> list[dict]:
    """Internal: hybrid FTS + vector with RRF reranking."""
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
        # filter narrows things. RRF reranker would crash without anchors.
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
