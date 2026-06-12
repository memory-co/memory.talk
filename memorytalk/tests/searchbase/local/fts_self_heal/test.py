"""fts_self_heal — broken-on-disk FTS index must rebuild, not 500.

See ``README.md``: this is the regression test for the 1.0.0 incident
where a 0.8.x install with a partially-missing index dir crashed every
search with "Index name 'text_idx' already exists".
"""
from __future__ import annotations

from pathlib import Path

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import get_embedder
from memorytalk.searchbase import Doc, LocalSearchBackend, Query


async def _open_backend(config: Config) -> LocalSearchBackend:
    return await LocalSearchBackend.create(
        data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim,
        embedder=get_embedder(config),
        collections={"cards": {"fields": {}}},
    )


@pytest.mark.asyncio
async def test_search_survives_partially_deleted_index(data_root):
    config = Config(data_root)
    config.ensure_dirs()

    # 1. Healthy lifecycle: write docs, search once so the FTS index
    #    gets created on disk.
    backend = await _open_backend(config)
    await backend.upsert("cards", [
        Doc(id=f"c{i}", text=f"hello world insight {i}") for i in range(20)
    ])
    hits = await backend.search("cards", Query(text="hello", top_k=5))
    assert hits, "sanity: healthy search must return hits"
    await backend.close()

    # 2. Break the index the way the 0.8.x EMFILE era did: the index
    #    dir + manifest entry survive, but a tokens file is gone.
    #    lance 4.0 then OMITS the index from list_indices (with a WARN)
    #    while its name still occupies the manifest.
    idx_root = Path(config.vectors_dir) / "cards.lance" / "_indices"
    tokens_files = sorted(idx_root.glob("*/*tokens*"))
    assert tokens_files, "sanity: FTS index files must exist on disk"
    tokens_files[0].unlink()

    # 3. Reopen (fresh memo, like a server restart) and search again.
    #    Must self-heal — rebuild the index and answer — not raise
    #    "Index name 'text_idx' already exists".
    backend2 = await _open_backend(config)
    try:
        hits2 = await backend2.search("cards", Query(text="hello", top_k=5))
        assert hits2, "post-heal search must return hits again"
    finally:
        await backend2.close()
