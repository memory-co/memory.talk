"""validate_embedder — dummy provider passes without any network call."""
from __future__ import annotations

from memory_talk_v2.config import Config
from memory_talk_v2.provider.embedding import validate_embedder


async def test_dummy_passes(tmp_path):
    (tmp_path / "settings.json").write_text('{"embedding": {"provider": "dummy"}}')
    await validate_embedder(Config(tmp_path))
