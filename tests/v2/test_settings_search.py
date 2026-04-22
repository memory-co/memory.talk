from memory_talk.config import Config, Settings, SearchConfig


def test_search_config_defaults():
    sc = SearchConfig()
    assert sc.default_top_k == 10
    assert sc.comment_max_length == 500
    assert sc.search_log_retention_days == 0


def test_settings_has_search_section(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = Config(str(tmp_path / ".memory-talk"))
    assert cfg.settings.search.default_top_k == 10


def test_settings_search_override_from_json(tmp_path):
    data_root = tmp_path / ".memory-talk"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        '{"search": {"default_top_k": 20}}'
    )
    cfg = Config(str(data_root))
    assert cfg.settings.search.default_top_k == 20
    assert cfg.settings.search.comment_max_length == 500  # default preserved
