import pytest
from unittest.mock import MagicMock, patch

from memory_talk_v2.config import Config
from memory_talk_v2.embedding import validate_embedder, EmbedderValidationError


def test_dummy_passes(tmp_path):
    (tmp_path / "settings.json").write_text('{"embedding": {"provider": "dummy"}}')
    validate_embedder(Config(tmp_path))


def test_openai_missing_env(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )
    with pytest.raises(EmbedderValidationError, match="UNIT_TEST_KEY"):
        validate_embedder(Config(tmp_path))


def test_openai_probe_dim_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )
    with patch("memory_talk_v2.embedding.httpx.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 384}]}
        mock_post.return_value = resp
        with pytest.raises(EmbedderValidationError, match="dim mismatch"):
            validate_embedder(Config(tmp_path))


def test_openai_probe_success(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )
    with patch("memory_talk_v2.embedding.httpx.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 1024}]}
        mock_post.return_value = resp
        validate_embedder(Config(tmp_path))
