"""LanceDB vector store for card embeddings."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import pyarrow as pa


class LanceStore:
    TABLE = "cards"

    def __init__(self, data_dir: Path):
        import lancedb

        self.db = lancedb.connect(str(data_dir))
        self._schema = pa.schema(
            [
                pa.field("card_id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32())),
            ]
        )

    def _table_exists(self) -> bool:
        try:
            names = list(self.db.table_names())
            return self.TABLE in names
        except Exception:
            return False

    def _get_or_create_table(self):
        if self._table_exists():
            return self.db.open_table(self.TABLE)
        return self.db.create_table(self.TABLE, schema=self._schema)

    def add(self, card_id: str, text: str, embedding: list[float]) -> None:
        table = self._get_or_create_table()
        table.add(
            [{"card_id": card_id, "text": text, "vector": embedding}]
        )

    def search(
        self, query: list[float], top_k: int = 5
    ) -> list[dict]:
        if not self._table_exists():
            return []
        table = self.db.open_table(self.TABLE)
        results = (
            table.search(query)
            .limit(top_k)
            .to_list()
        )
        return results

    def delete(self, card_ids: list[str]) -> None:
        if not self._table_exists():
            return
        table = self.db.open_table(self.TABLE)
        filter_expr = " OR ".join(
            [f"card_id = '{cid}'" for cid in card_ids]
        )
        table.delete(filter_expr)
