import sqlite3

import pytest

from memory_talk_v2.config import Config, ConfigValidationError


def test_default_data_root_layout(tmp_path):
    cfg = Config(tmp_path / ".mt")
    assert cfg.data_root == tmp_path / ".mt"
    assert cfg.db_path.name == "memory.db"
    assert cfg.vectors_dir.name == "vectors"
    assert cfg.sessions_dir.name == "sessions"
    assert cfg.cards_dir.name == "cards"
    assert cfg.links_dir.name == "links"
    assert cfg.search_log_dir == cfg.data_root / "logs" / "search"
    assert cfg.event_log_dir == cfg.data_root / "logs" / "events"


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


def test_validate_passes_on_empty_root(tmp_path):
    Config(tmp_path / ".mt").validate()  # no memory.db yet


def test_validate_rejects_v1_residue(tmp_path):
    root = tmp_path / ".mt"
    root.mkdir()
    # Simulate v1 residue by creating a recall_log table
    conn = sqlite3.connect(root / "memory.db")
    conn.execute("CREATE TABLE recall_log (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    with pytest.raises(ConfigValidationError) as e:
        Config(root).validate()
    assert "recall_log" in str(e.value)


def test_ensure_dirs_creates_expected_layout(tmp_path):
    cfg = Config(tmp_path / ".mt")
    cfg.ensure_dirs()
    for p in [cfg.vectors_dir, cfg.sessions_dir, cfg.cards_dir,
              cfg.links_dir, cfg.search_log_dir, cfg.event_log_dir]:
        assert p.exists()
