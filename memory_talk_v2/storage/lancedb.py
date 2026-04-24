"""Async LanceDB store for card vectors + FTS, and session FTS.

Only cards have vector embeddings. Sessions are FTS-only.
Uses lancedb.connect_async for true async I/O throughout.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import pyarrow as pa


def _segment(text: str) -> str:
    """jieba 预分词,空格连接。同步(jieba.cut 是纯 CPU,亚毫秒级)。"""
    import jieba
    return " ".join(jieba.cut(text or ""))


def _in_clause(ids: list[str], column: str) -> Optional[str]:
    if not ids:
        return None
    quoted = ", ".join("'" + i.replace("'", "''") + "'" for i in ids)
    return f"{column} IN ({quoted})"


class LanceStore:
    CARDS = "cards"
    SESSIONS = "sessions"

    def __init__(self, db, data_dir: Path, dim: int):
        self.db = db
        self.data_dir = data_dir
        self.dim = dim
        self._cards_schema = pa.schema([
            pa.field("card_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ])
        self._sessions_schema = pa.schema([
            pa.field("session_id", pa.string()),
            pa.field("text", pa.string()),
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

    async def _get_or_create_sessions(self):
        if await self._exists(self.SESSIONS):
            return await self.db.open_table(self.SESSIONS)
        return await self.db.create_table(self.SESSIONS, schema=self._sessions_schema)

    # ---------- cards ----------

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

    async def drop_cards(self) -> None:
        if await self._exists(self.CARDS):
            await self.db.drop_table(self.CARDS)

    async def hybrid_search_cards(
        self,
        vector: list[float],
        text: str,
        whitelist: Optional[list[str]] = None,
        top_k: int = 10,
    ) -> list[dict]:
        """FTS + vector hybrid with RRF reranker. whitelist is card_id pre-filter."""
        if not await self._exists(self.CARDS):
            return []
        from lancedb.rerankers import RRFReranker

        table = await self.db.open_table(self.CARDS)
        builder = (
            await table.query()
            .nearest_to(vector)
            .nearest_to_text(_segment(text))
            .rerank(reranker=RRFReranker(K=60))
            .limit(top_k)
        ) if False else None  # async builder chain is slightly different

        # Async LanceDB hybrid search: use the explicit query builder API.
        q = table.query().nearest_to(vector).nearest_to_text(_segment(text))
        where_expr = _in_clause(whitelist, "card_id") if whitelist is not None else None
        if where_expr:
            q = q.where(where_expr)
        q = q.rerank(reranker=RRFReranker(K=60)).limit(top_k)
        return await q.to_list()

    # ---------- sessions ----------

    async def add_session(self, session_id: str, text: str) -> None:
        table = await self._get_or_create_sessions()
        await table.delete(f"session_id = '{session_id}'")
        await table.add([{"session_id": session_id, "text": _segment(text)}])

    async def delete_sessions(self, session_ids: list[str]) -> None:
        if not await self._exists(self.SESSIONS) or not session_ids:
            return
        table = await self.db.open_table(self.SESSIONS)
        expr = " OR ".join(f"session_id = '{sid}'" for sid in session_ids)
        await table.delete(expr)

    async def drop_sessions(self) -> None:
        if await self._exists(self.SESSIONS):
            await self.db.drop_table(self.SESSIONS)

    async def fts_search_sessions(
        self,
        text: str,
        whitelist: Optional[list[str]] = None,
        top_k: int = 10,
    ) -> list[dict]:
        if not await self._exists(self.SESSIONS):
            return []
        table = await self.db.open_table(self.SESSIONS)
        q = table.query().nearest_to_text(_segment(text))
        where_expr = _in_clause(whitelist, "session_id") if whitelist is not None else None
        if where_expr:
            q = q.where(where_expr)
        q = q.limit(top_k)
        return await q.to_list()

    # ---------- FTS index maintenance ----------

    async def ensure_fts_index(self, table_name: str, replace: bool = False) -> None:
        """Create (or rebuild) an FTS inverted index on `text`.

        Idempotent. If an index exists and `replace` is False, just run
        optimize() to absorb any appended rows since the last index build.
        `replace=True` drops and rebuilds the index (used by /v2/rebuild).
        """
        if not await self._exists(table_name):
            return
        from lancedb.index import FTS

        table = await self.db.open_table(table_name)

        has_fts = False
        try:
            indices = await table.list_indices()
            for idx in indices:
                cols = getattr(idx, "columns", None) or []
                if "text" in cols:
                    has_fts = True
                    break
        except Exception:
            pass

        if has_fts and not replace:
            try:
                await table.optimize()
            except Exception:
                pass
            return

        await table.create_index(
            "text",
            config=FTS(base_tokenizer="whitespace", with_position=True),
            replace=True,
        )
