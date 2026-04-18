"""Dispatch tests for get_embedder."""
from __future__ import annotations
import pytest
from memory_talk.config import Config
from memory_talk.embedding import (
    DummyEmbedder,
    OpenAIEmbedder,
    get_embedder,
)


def test_dispatch_dummy(temp_root):
    c = Config(temp_root)
    c.settings.embedding.provider = "dummy"
    assert isinstance(get_embedder(c), DummyEmbedder)


def test_dispatch_openai_constructs_correctly(temp_root, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "sk-test")
    c = Config(temp_root)
    c.settings.embedding.provider = "openai"
    c.settings.embedding.endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    c.settings.embedding.auth_env_key = "QWEN_KEY"
    c.settings.embedding.model = "text-embedding-v4"
    c.settings.embedding.timeout = 12.5

    e = get_embedder(c)
    assert isinstance(e, OpenAIEmbedder)
    assert e.endpoint == "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    assert e.auth_env_key == "QWEN_KEY"
    assert e.model == "text-embedding-v4"
    assert e.timeout == 12.5


def test_dispatch_openai_missing_endpoint_raises(temp_root):
    c = Config(temp_root)
    c.settings.embedding.provider = "openai"
    c.settings.embedding.auth_env_key = "QWEN_KEY"
    with pytest.raises(ValueError, match="endpoint"):
        get_embedder(c)


def test_dispatch_openai_missing_auth_env_key_raises(temp_root):
    c = Config(temp_root)
    c.settings.embedding.provider = "openai"
    c.settings.embedding.endpoint = "https://example.com/v1/embeddings"
    with pytest.raises(ValueError, match="auth_env_key"):
        get_embedder(c)


def test_dispatch_unknown_raises(temp_root):
    c = Config(temp_root)
    c.settings.embedding.provider = "nope"
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedder(c)
