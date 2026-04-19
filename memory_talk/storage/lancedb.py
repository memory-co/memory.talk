"""LanceDB store for card embeddings and session full-text."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import pyarrow as pa


def _segment(text: str) -> str:
    """jieba 预分词，空格连接。中文按词切、英文/数字/标点保留，之后用 whitespace FTS 索引。"""
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

    def __init__(self, data_dir: Path, dim: int = 384):
        import lancedb

        self.db = lancedb.connect(str(data_dir))
        self._cards_schema = pa.schema(
            [
                pa.field("card_id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
            ]
        )
        self._sessions_schema = pa.schema(
            [
                pa.field("session_id", pa.string()),
                pa.field("text", pa.string()),
            ]
        )

    # ---------- table management ----------

    def _exists(self, name: str) -> bool:
        try:
            return name in self.db.list_tables().tables
        except Exception:
            return False

    def _get_or_create_cards(self):
        if self._exists(self.CARDS):
            return self.db.open_table(self.CARDS)
        return self.db.create_table(self.CARDS, schema=self._cards_schema)

    def _get_or_create_sessions(self):
        if self._exists(self.SESSIONS):
            return self.db.open_table(self.SESSIONS)
        return self.db.create_table(self.SESSIONS, schema=self._sessions_schema)

    # ---------- cards ----------

    def add(self, card_id: str, text: str, embedding: list[float]) -> None:
        """Add a card. Text is jieba-segmented before indexing."""
        table = self._get_or_create_cards()
        table.add([{"card_id": card_id, "text": _segment(text), "vector": embedding}])

    def search(self, query: list[float], top_k: int = 5) -> list[dict]:
        """Pure vector similarity (legacy path used by `recall`)."""
        if not self._exists(self.CARDS):
            return []
        table = self.db.open_table(self.CARDS)
        return (
            table.search(query, vector_column_name="vector")
            .limit(top_k)
            .to_list()
        )

    def delete(self, card_ids: list[str]) -> None:
        if not self._exists(self.CARDS) or not card_ids:
            return
        table = self.db.open_table(self.CARDS)
        expr = " OR ".join(f"card_id = '{cid}'" for cid in card_ids)
        table.delete(expr)

    def hybrid_search_cards(
        self,
        vector: list[float],
        text: str,
        whitelist: Optional[list[str]] = None,
        top_k: int = 10,
    ) -> list[dict]:
        """FTS + vector hybrid with RRF reranker. whitelist is card_id pre-filter."""
        if not self._exists(self.CARDS):
            return []
        from lancedb.rerankers import RRFReranker

        table = self.db.open_table(self.CARDS)
        builder = (
            table.search(query_type="hybrid")
            .vector(vector)
            .text(_segment(text))
        )
        where_expr = _in_clause(whitelist, "card_id") if whitelist is not None else None
        if where_expr:
            builder = builder.where(where_expr)
        return (
            builder.limit(top_k)
            .rerank(reranker=RRFReranker(K=60))
            .to_list()
        )

    # ---------- sessions ----------

    def add_session(self, session_id: str, text: str) -> None:
        """Add / refresh a session's full text. Replaces prior row if present."""
        table = self._get_or_create_sessions()
        # upsert: delete existing then add
        table.delete(f"session_id = '{session_id}'")
        table.add([{"session_id": session_id, "text": _segment(text)}])

    def delete_session(self, session_ids: list[str]) -> None:
        if not self._exists(self.SESSIONS) or not session_ids:
            return
        table = self.db.open_table(self.SESSIONS)
        expr = " OR ".join(f"session_id = '{sid}'" for sid in session_ids)
        table.delete(expr)

    def fts_search_sessions(
        self,
        text: str,
        whitelist: Optional[list[str]] = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Pure FTS over session rounds text. whitelist is session_id pre-filter."""
        if not self._exists(self.SESSIONS):
            return []
        table = self.db.open_table(self.SESSIONS)
        builder = table.search(_segment(text), query_type="fts")
        where_expr = _in_clause(whitelist, "session_id") if whitelist is not None else None
        if where_expr:
            builder = builder.where(where_expr)
        return builder.limit(top_k).to_list()

    # ---------- FTS index maintenance ----------

    def ensure_fts_index(self, table_name: str, replace: bool = False) -> None:
        """Build FTS index on `text` column. Idempotent when replace=False."""
        if not self._exists(table_name):
            return
        table = self.db.open_table(table_name)
        if not replace:
            try:
                for idx in table.list_indices():
                    # existing FTS on `text` column — skip
                    if "text" in getattr(idx, "columns", []):
                        return
            except Exception:
                pass
        table.create_fts_index(
            "text",
            use_tantivy=False,
            base_tokenizer="whitespace",
            with_position=True,
            replace=replace,
        )
