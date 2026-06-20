"""reembed — backend rebuild_collection / vector_index_dim scenarios.

Drives ``LocalSearchBackend.rebuild_collection`` directly with custom
embedders so the per-row-failure isolation and total-provider-down abort
contracts are unit-tested without the HTTP layer.
"""
from __future__ import annotations

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import Embedder
from memorytalk.searchbase import Doc, LocalSearchBackend
from memorytalk.tests.searchbase.local.conftest import make_backend


class _CountingEmbedder(Embedder):
    """Deterministic vectors; counts calls so a rebuild is observable."""

    def __init__(self, dim: int = 384, value: float = 0.5):
        self.dim = dim
        self.value = value
        self.calls = 0

    async def embed(self, texts):
        self.calls += len(texts)
        return [[self.value] * self.dim for _ in texts]


class _FlakyEmbedder(Embedder):
    """Raises a plain Exception (per-object failure) for texts containing
    ``bad`` — but never a ConnectionError, so the run must not abort."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    async def embed(self, texts):
        out = []
        for t in texts:
            if "bad" in t:
                raise ValueError("simulated per-object embed failure")
            out.append([0.1] * self.dim)
        return out


class _DownEmbedder(Embedder):
    """Provider wholly unavailable after ``ok_for`` successful rows."""

    def __init__(self, dim: int = 384, ok_for: int = 1):
        self.dim = dim
        self.ok_for = ok_for
        self.calls = 0

    async def embed(self, texts):
        out = []
        for _ in texts:
            if self.calls >= self.ok_for:
                raise ConnectionError("provider down")
            self.calls += 1
            out.append([0.2] * self.dim)
        return out


async def _backend_with(config, embedder, collections=None):
    return await LocalSearchBackend.create(
        data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim,
        embedder=embedder,
        collections=collections or {"cards": {"fields": {}}},
    )


# ────────── happy path: every row re-embedded + vector overwritten ──────────

async def test_rebuild_reembeds_every_row(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    b = await make_backend(config, collections={"cards": {"fields": {}}})
    try:
        await b.upsert("cards", [
            Doc(id="c1", text="alpha"),
            Doc(id="c2", text="beta"),
            Doc(id="c3", text="gamma"),
        ])
        seen = []
        processed, failed = await b.rebuild_collection(
            "cards", on_progress=seen.append,
        )
        assert (processed, failed) == (3, 0)
        # progress fired once per successful row, monotonically.
        assert seen == [1, 2, 3]
        # row count unchanged — overwrite, not append.
        assert await b.count("cards") == 3
    finally:
        await b.close()


# ────────── per-object failure is isolated, run continues ──────────

async def test_rebuild_isolates_per_object_failure(data_root):
    # Seed rows with a GOOD embedder (one row's stored text contains
    # "bad"), then rebuild with a flaky one that rejects only that row.
    config = Config(data_root)
    config.ensure_dirs()
    b_seed = await _backend_with(config, _CountingEmbedder())
    try:
        await b_seed.upsert("cards", [
            Doc(id="g1", text="good row one"),
            Doc(id="g2", text="this is bad and fails"),
            Doc(id="g3", text="good row three"),
        ])
    finally:
        await b_seed.close()

    b = await _backend_with(Config(data_root), _FlakyEmbedder())
    try:
        processed, failed = await b.rebuild_collection("cards")
        # 2 good rows re-embedded, 1 bad row counted as failed, no abort.
        assert processed == 2
        assert failed == 1
        assert await b.count("cards") == 3  # nothing dropped
    finally:
        await b.close()


# ────────── wholly-unavailable provider aborts (ConnectionError) ──────────

async def test_rebuild_aborts_on_connection_error(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    b = await _backend_with(config, _CountingEmbedder())
    try:
        await b.upsert("cards", [
            Doc(id="c1", text="one"),
            Doc(id="c2", text="two"),
            Doc(id="c3", text="three"),
        ])
    finally:
        await b.close()

    # Provider down after the first row → ConnectionError must propagate.
    b2 = await _backend_with(Config(data_root), _DownEmbedder(ok_for=1))
    try:
        with pytest.raises(ConnectionError):
            await b2.rebuild_collection("cards")
    finally:
        await b2.close()


# ────────── vector_index_dim reflects on-disk width ──────────

async def test_vector_index_dim_reads_disk(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    b = await make_backend(config, collections={"cards": {"fields": {}}})
    try:
        await b.upsert("cards", [Doc(id="c1", text="x")])
        assert await b.vector_index_dim("cards") == config.settings.embedding.dim
        # Absent collection → None.
        assert await b.vector_index_dim("nope") is None
    finally:
        await b.close()
