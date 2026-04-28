"""Config — data_root layout properties + ensure_dirs() side effect."""
from __future__ import annotations

from memorytalk.config import Config


def test_default_data_root_layout(tmp_path):
    cfg = Config(tmp_path / ".mt")
    assert cfg.data_root == tmp_path / ".mt"
    assert cfg.db_path.name == "memory.db"
    assert cfg.vectors_dir.name == "vectors"
    assert cfg.sessions_dir.name == "sessions"
    assert cfg.cards_dir.name == "cards"
    assert cfg.links_dir.name == "links"
    assert cfg.search_log_dir == cfg.data_root / "logs" / "search"


def test_ensure_dirs_creates_expected_layout(tmp_path):
    cfg = Config(tmp_path / ".mt")
    cfg.ensure_dirs()
    for p in [cfg.vectors_dir, cfg.sessions_dir, cfg.cards_dir,
              cfg.links_dir, cfg.search_log_dir]:
        assert p.exists()
