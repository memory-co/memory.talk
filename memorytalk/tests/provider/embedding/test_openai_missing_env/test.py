"""validate_embedder — openai provider fails fast when auth env var is missing."""
from __future__ import annotations

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import EmbedderValidationError, validate_embedder


async def test_openai_missing_env(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )
    with pytest.raises(EmbedderValidationError, match="UNIT_TEST_KEY"):
        await validate_embedder(Config(tmp_path))
