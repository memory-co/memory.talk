"""validate_embedder — openai HTTP probe checks endpoint and embedding dim."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import EmbedderValidationError, validate_embedder


def _mock_client_returning(embedding: list[float]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": [{"index": 0, "embedding": embedding}]}

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=resp)
    return client


def _write_openai_settings(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )


async def test_openai_probe_dim_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    _write_openai_settings(tmp_path)
    with patch("memorytalk.provider.embedding.httpx.AsyncClient",
               return_value=_mock_client_returning([0.1] * 384)):
        with pytest.raises(EmbedderValidationError, match="dim mismatch"):
            await validate_embedder(Config(tmp_path))


async def test_openai_probe_success(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    _write_openai_settings(tmp_path)
    with patch("memorytalk.provider.embedding.httpx.AsyncClient",
               return_value=_mock_client_returning([0.1] * 1024)):
        await validate_embedder(Config(tmp_path))
