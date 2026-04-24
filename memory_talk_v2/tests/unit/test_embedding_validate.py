from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory_talk_v2.config import Config
from memory_talk_v2.provider.embedding import validate_embedder, EmbedderValidationError


async def test_dummy_passes(tmp_path):
    (tmp_path / "settings.json").write_text('{"embedding": {"provider": "dummy"}}')
    await validate_embedder(Config(tmp_path))


async def test_openai_missing_env(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )
    with pytest.raises(EmbedderValidationError, match="UNIT_TEST_KEY"):
        await validate_embedder(Config(tmp_path))


async def test_openai_probe_dim_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )

    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 384}]}

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=resp)

    with patch("memory_talk_v2.provider.embedding.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(EmbedderValidationError, match="dim mismatch"):
            await validate_embedder(Config(tmp_path))


async def test_openai_probe_success(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )

    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 1024}]}

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=resp)

    with patch("memory_talk_v2.provider.embedding.httpx.AsyncClient", return_value=mock_client):
        await validate_embedder(Config(tmp_path))
