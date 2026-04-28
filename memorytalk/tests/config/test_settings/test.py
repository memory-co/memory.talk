"""Config.settings — defaults + settings.json overrides."""
from __future__ import annotations

from memorytalk.config import Config


def test_settings_defaults(tmp_path):
    cfg = Config(tmp_path / ".mt")
    assert cfg.settings.server.port == 7788
    assert cfg.settings.search.default_top_k == 10
    assert cfg.settings.embedding.provider == "dummy"


def test_settings_loaded_from_json(tmp_path):
    root = tmp_path / ".mt"
    root.mkdir()
    (root / "settings.json").write_text(
        '{"search": {"default_top_k": 42}, "embedding": {"provider": "local", "dim": 768}}'
    )
    cfg = Config(root)
    assert cfg.settings.search.default_top_k == 42
    assert cfg.settings.embedding.provider == "local"
    assert cfg.settings.embedding.dim == 768
