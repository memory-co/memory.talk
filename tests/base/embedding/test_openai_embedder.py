"""Unit tests for OpenAIEmbedder — HTTP is mocked, no network."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from memory_talk.embedding import OpenAIEmbedder


def _mock_response(vectors: list[list[float]]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "data": [{"embedding": v, "index": i} for i, v in enumerate(vectors)],
        "model": "text-embedding-v4",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }
    return resp


def test_embed_posts_to_endpoint_with_bearer(monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "sk-test-123")
    e = OpenAIEmbedder(
        endpoint="https://example.com/v1/embeddings",
        auth_env_key="QWEN_KEY",
        model="text-embedding-v4",
        timeout=5.0,
    )
    with patch("memory_talk.embedding.httpx.post") as post:
        post.return_value = _mock_response([[0.1, 0.2, 0.3]])
        out = e.embed(["hello"])

    assert out == [[0.1, 0.2, 0.3]]
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "https://example.com/v1/embeddings"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test-123"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["json"] == {
        "model": "text-embedding-v4",
        "input": ["hello"],
        "encoding_format": "float",
    }
    assert kwargs["timeout"] == 5.0


def test_embed_preserves_order_by_index(monkeypatch):
    """OpenAI API may return `data` in any order; must sort by `index`."""
    monkeypatch.setenv("QWEN_KEY", "sk-test-123")
    e = OpenAIEmbedder(
        endpoint="https://example.com/v1/embeddings",
        auth_env_key="QWEN_KEY",
        model="m",
    )
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "data": [
            {"embedding": [2.0], "index": 1},
            {"embedding": [1.0], "index": 0},
        ]
    }
    with patch("memory_talk.embedding.httpx.post", return_value=resp):
        out = e.embed(["a", "b"])
    assert out == [[1.0], [2.0]]


def test_embed_batch_multiple_inputs(monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "sk-test-123")
    e = OpenAIEmbedder(
        endpoint="https://example.com/v1/embeddings",
        auth_env_key="QWEN_KEY",
        model="m",
    )
    with patch("memory_talk.embedding.httpx.post") as post:
        post.return_value = _mock_response([[0.1], [0.2], [0.3]])
        out = e.embed(["x", "y", "z"])
    assert out == [[0.1], [0.2], [0.3]]
    _, kwargs = post.call_args
    assert kwargs["json"]["input"] == ["x", "y", "z"]


def test_missing_env_var_raises():
    # Ensure the env var is absent.
    import os
    os.environ.pop("NO_SUCH_KEY_123", None)
    e = OpenAIEmbedder(
        endpoint="https://example.com/v1/embeddings",
        auth_env_key="NO_SUCH_KEY_123",
        model="m",
    )
    with pytest.raises(RuntimeError, match="NO_SUCH_KEY_123"):
        e.embed(["hello"])


def test_http_error_propagates(monkeypatch):
    import httpx
    monkeypatch.setenv("QWEN_KEY", "sk-test-123")
    e = OpenAIEmbedder(
        endpoint="https://example.com/v1/embeddings",
        auth_env_key="QWEN_KEY",
        model="m",
    )
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=MagicMock(status_code=401)
    )
    with patch("memory_talk.embedding.httpx.post", return_value=resp):
        with pytest.raises(httpx.HTTPStatusError):
            e.embed(["hello"])
