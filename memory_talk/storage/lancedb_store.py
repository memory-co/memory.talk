"""LanceDB implementation of VectorStore."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from memory_talk.storage.interfaces import VectorStore


class LanceDBVectorStore(VectorStore):
    TABLE_NAME = "cards"

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))

    def _table_exists(self) -> bool:
        try:
            self.db.open_table(self.TABLE_NAME)
            return True
        except Exception:
            return False

    def _ensure_table(self, vector_dim: int) -> lancedb.table.Table:
        if self._table_exists():
            return self.db.open_table(self.TABLE_NAME)
        schema = pa.schema([
            pa.field("card_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), vector_dim)),
            pa.field("session_id", pa.string()),
        ])
        return self.db.create_table(self.TABLE_NAME, schema=schema)

    def add_card(self, card_id: str, text: str, embedding: list[float], metadata: dict[str, Any] | None = None) -> None:
        table = self._ensure_table(len(embedding))
        table.add([{
            "card_id": card_id,
            "text": text,
            "vector": embedding,
            "session_id": (metadata or {}).get("session_id", ""),
        }])

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        if not self._table_exists():
            return []
        table = self.db.open_table(self.TABLE_NAME)
        results = table.search(query_embedding).limit(top_k).to_list()
        return [
            {
                "card_id": r["card_id"],
                "text": r["text"],
                "session_id": r["session_id"],
                "distance": r.get("_distance", 0.0),
            }
            for r in results
        ]

    def delete_cards(self, card_ids: list[str]) -> None:
        if not self._table_exists():
            return
        table = self.db.open_table(self.TABLE_NAME)
        ids_str = ", ".join(f"'{cid}'" for cid in card_ids)
        table.delete(f"card_id IN ({ids_str})")
