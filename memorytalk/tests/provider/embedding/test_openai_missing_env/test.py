"""Server startup fails fast when an auth env var is missing.

The error is raised at config load (``_load_settings``) now, not inside
``validate_embedder`` — env-var rendering happens at the disk-load
boundary, not at request time. ``validate_embedder`` accesses
``config.settings``, which triggers the load + render.
"""
from __future__ import annotations

import pytest

from memorytalk.config import Config, ConfigValidationError
from memorytalk.provider.embedding import validate_embedder


async def test_openai_missing_env(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_key": "${UNIT_TEST_KEY}", "model": "x", "dim": 1024}}'
    )
    with pytest.raises(ConfigValidationError, match="UNIT_TEST_KEY"):
        await validate_embedder(Config(tmp_path))
