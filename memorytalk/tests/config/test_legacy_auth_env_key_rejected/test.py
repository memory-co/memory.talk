"""Strict migration: a settings.json carrying the legacy
``embedding.auth_env_key`` field must refuse to load. The user is told
to re-run ``memory-talk setup`` rather than have the field silently
turn into an empty literal at request time.
"""
from __future__ import annotations
import json

import pytest

from memorytalk.config import Config, ConfigValidationError


def test_legacy_auth_env_key_field_is_rejected(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {
            "provider": "openai",
            "endpoint": "https://x/v1/embeddings",
            "auth_env_key": "QWEN_KEY",   # ← legacy
            "model": "text-embedding-v4",
            "dim": 1024,
        },
    }))
    cfg = Config(tmp_path)
    with pytest.raises(ConfigValidationError, match="auth_env_key"):
        _ = cfg.settings


def test_new_auth_key_field_loads_fine(tmp_path):
    """Literal value flows through unchanged. Env-var rendering is a
    separate concern, covered in tests/config/test_env_var_rendering."""
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {
            "provider": "openai",
            "endpoint": "https://x/v1/embeddings",
            "auth_key": "sk-literal-test-key",
            "model": "text-embedding-v4",
            "dim": 1024,
        },
    }))
    cfg = Config(tmp_path)
    assert cfg.settings.embedding.auth_key == "sk-literal-test-key"
