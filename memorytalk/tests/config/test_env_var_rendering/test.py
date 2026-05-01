"""Config-layer ${VAR} rendering at disk load.

When settings.json contains ``${VAR}`` references in ``auth_key``,
``Config._load_settings`` must render them against ``os.environ`` so
the rest of the codebase treats the field as a literal API key. The
disk file remains untouched (raw template); rendering happens only on
the live process's view.

Provider code (``OpenAIEmbedder`` / ``validate_embedder``) deliberately
does NOT render — keeping rendering at the disk-load boundary makes the
active key visible from one place and avoids cross-process-context
mismatches.
"""
from __future__ import annotations
import json

import pytest

from memorytalk.config import Config, ConfigValidationError


def _write_settings(tmp_path, auth_key: str) -> None:
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {
            "provider": "openai",
            "endpoint": "https://x/v1/embeddings",
            "auth_key": auth_key,
            "model": "text-embedding-v4",
            "dim": 1024,
        },
    }))


def test_brace_form_renders_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV_RENDER_TEST_X", "sk-rendered-1")
    _write_settings(tmp_path, "${ENV_RENDER_TEST_X}")
    cfg = Config(tmp_path)
    assert cfg.settings.embedding.auth_key == "sk-rendered-1"


def test_bare_form_renders_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV_RENDER_TEST_Y", "sk-rendered-2")
    _write_settings(tmp_path, "$ENV_RENDER_TEST_Y")
    cfg = Config(tmp_path)
    assert cfg.settings.embedding.auth_key == "sk-rendered-2"


def test_literal_passes_through_unchanged(tmp_path):
    _write_settings(tmp_path, "sk-literal-zzz")
    cfg = Config(tmp_path)
    assert cfg.settings.embedding.auth_key == "sk-literal-zzz"


def test_missing_env_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("ENV_RENDER_TEST_MISSING", raising=False)
    _write_settings(tmp_path, "${ENV_RENDER_TEST_MISSING}")
    cfg = Config(tmp_path)
    with pytest.raises(ConfigValidationError, match="ENV_RENDER_TEST_MISSING"):
        _ = cfg.settings


def test_disk_content_is_not_mutated(tmp_path, monkeypatch):
    """Rendering happens on the in-memory Settings, not on the file."""
    monkeypatch.setenv("ENV_RENDER_TEST_KEEP", "sk-rendered")
    _write_settings(tmp_path, "${ENV_RENDER_TEST_KEEP}")
    cfg = Config(tmp_path)
    _ = cfg.settings  # trigger load + render
    on_disk = json.loads((tmp_path / "settings.json").read_text())
    assert on_disk["embedding"]["auth_key"] == "${ENV_RENDER_TEST_KEEP}"
