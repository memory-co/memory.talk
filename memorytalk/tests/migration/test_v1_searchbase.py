"""v1 searchbase migration — 0.8.x LanceDB layout → v1 columns.

These tests open a raw LanceDB (no LocalSearchBackend yet) with the
0.8.x table shape, then build a backend over the same data_dir so its
``admin()`` can run the v1 up. The asserts are about the columns
present after migration — we don't write or read rows here; the
search hot path is exercised by the basic_io scenario.
"""
from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest

from memorytalk.migrations.v1 import up_searchbase
from memorytalk.searchbase import LocalSearchBackend


class _DummyEmbedder:
    """Embedder stub — never invoked here, but ``LocalSearchBackend``
    requires a non-None one. Returns deterministic zero vectors."""

    def __init__(self, dim: int):
        self.dim = dim

    async def embed(self, texts):
        return [[0.0] * self.dim for _ in texts]

    async def embed_one(self, text):
        return [0.0] * self.dim


def _cards_081_schema(dim: int) -> pa.Schema:
    return pa.schema([
        pa.field("card_id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])


def _rounds_081_schema(dim: int) -> pa.Schema:
    return pa.schema([
        pa.field("session_id", pa.string()),
        pa.field("idx", pa.int32()),
        pa.field("role", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])


async def _seed_081_lancedb(data_dir: Path, dim: int) -> None:
    import lancedb

    data_dir.mkdir(parents=True, exist_ok=True)
    db = await lancedb.connect_async(str(data_dir))
    await db.create_table("cards", schema=_cards_081_schema(dim))
    await db.create_table("rounds", schema=_rounds_081_schema(dim))


# ─── tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_up_renames_cards_card_id_to_id(tmp_path):
    dim = 4
    data_dir = tmp_path / "vectors"
    await _seed_081_lancedb(data_dir, dim)

    # Build the backend over the seeded data_dir; the constructor
    # auto-creates declared collections that don't exist, but since
    # both already exist (with 0.8.x columns), it leaves them alone.
    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections={
            "cards": {"fields": {}},
            "rounds": {
                "fields": {"session_id": "str", "idx": "int", "role": "str"},
                "auto_split": True,
            },
        },
    )
    try:
        admin = backend.admin()
        # Sanity: pre-migration cards has card_id, no id.
        cols_before = set(await admin.list_columns("cards"))
        assert "card_id" in cols_before and "id" not in cols_before

        await up_searchbase.run(admin)

        cols_after = set(await admin.list_columns("cards"))
        assert "id" in cols_after
        assert "card_id" not in cols_after
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_up_adds_rounds_id_base_id_chunk(tmp_path):
    dim = 4
    data_dir = tmp_path / "vectors"
    await _seed_081_lancedb(data_dir, dim)

    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections={
            "cards": {"fields": {}},
            "rounds": {
                "fields": {"session_id": "str", "idx": "int", "role": "str"},
                "auto_split": True,
            },
        },
    )
    try:
        admin = backend.admin()
        cols_before = set(await admin.list_columns("rounds"))
        assert "id" not in cols_before
        assert "_base_id" not in cols_before
        assert "_chunk" not in cols_before

        await up_searchbase.run(admin)

        cols_after = set(await admin.list_columns("rounds"))
        for needed in ("id", "_base_id", "_chunk"):
            assert needed in cols_after, f"rounds missing {needed}"
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_up_is_idempotent(tmp_path):
    """Running up twice (e.g. a botched first run that crashed after
    the rename but before recording state) doesn't error."""
    dim = 4
    data_dir = tmp_path / "vectors"
    await _seed_081_lancedb(data_dir, dim)
    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections={
            "cards": {"fields": {}},
            "rounds": {
                "fields": {"session_id": "str", "idx": "int", "role": "str"},
                "auto_split": True,
            },
        },
    )
    try:
        admin = backend.admin()
        await up_searchbase.run(admin)
        await up_searchbase.run(admin)  # must be a no-op
        cols = set(await admin.list_columns("cards"))
        assert "id" in cols and "card_id" not in cols
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_up_noop_on_fresh_backend(tmp_path):
    """Fresh install — LocalSearchBackend auto-creates collections with
    the v1 shape. up should see no work to do."""
    dim = 4
    data_dir = tmp_path / "vectors"
    backend = await LocalSearchBackend.create(
        data_dir=data_dir, dim=dim,
        embedder=_DummyEmbedder(dim),
        collections={
            "cards": {"fields": {}},
            "rounds": {
                "fields": {"session_id": "str", "idx": "int", "role": "str"},
                "auto_split": True,
            },
        },
    )
    try:
        admin = backend.admin()
        await up_searchbase.run(admin)
        cols = set(await admin.list_columns("cards"))
        assert "id" in cols and "card_id" not in cols
        rcols = set(await admin.list_columns("rounds"))
        for needed in ("id", "_base_id", "_chunk"):
            assert needed in rcols
    finally:
        await backend.close()
