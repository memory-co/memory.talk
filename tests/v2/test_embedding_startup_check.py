import pytest
from unittest.mock import patch, MagicMock
from memory_talk.config import Config
from memory_talk.embedding import validate_embedder, EmbedderValidationError


def test_dummy_validates(tmp_path):
    (tmp_path / "settings.json").write_text('{"embedding": {"provider": "dummy"}}')
    cfg = Config(str(tmp_path))
    # should not raise
    validate_embedder(cfg)


def test_openai_missing_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with pytest.raises(EmbedderValidationError, match="UNIT_TEST_KEY"):
        validate_embedder(cfg)


def test_openai_present_env_and_live_ping_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with patch("memory_talk.embedding.httpx.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 1024}]}
        mock_post.return_value = resp
        # should not raise
        validate_embedder(cfg)
        assert mock_post.called


def test_openai_live_ping_http_error(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with patch("memory_talk.embedding.httpx.post") as mock_post:
        mock_post.side_effect = httpx.ConnectError("network unreachable")
        with pytest.raises(EmbedderValidationError, match="network unreachable"):
            validate_embedder(cfg)


def test_openai_live_ping_dim_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with patch("memory_talk.embedding.httpx.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 384}]}  # wrong dim
        mock_post.return_value = resp
        with pytest.raises(EmbedderValidationError, match="dim mismatch"):
            validate_embedder(cfg)


def test_create_app_exits_on_missing_env(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    from memory_talk.api import create_app
    with pytest.raises(SystemExit) as excinfo:
        create_app(cfg)
    assert excinfo.value.code == 2
