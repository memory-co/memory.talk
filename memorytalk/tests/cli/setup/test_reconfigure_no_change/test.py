"""Reconfigure path with no field changes — settings.json must NOT be rewritten."""
from __future__ import annotations
import json


def _seed_settings(data_root):
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "settings.json").write_text(json.dumps({
        "server": {"port": 7788},
        "vector": {"provider": "lancedb"},
        "relation": {"provider": "sqlite"},
        "embedding": {
            "provider": "openai",
            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            "auth_key": "${QWEN_KEY}",
            "model": "text-embedding-v4",
            "dim": 1024,
            "timeout": 30.0,
        },
        "ttl": {"card": {"initial": 2592000, "factor": 2.0, "max": 31536000},
                "link": {"initial": 1209600, "factor": 2.0, "max": 15768000}},
        "search": {"default_top_k": 10, "comment_max_length": 500, "search_log_retention_days": 0},
    }, indent=2))


def test_reconfigure_no_change_does_not_rewrite(setup_env):
    setup_env.mock_openai_probe(dim=1024)
    _seed_settings(setup_env.data_root)
    settings_path = setup_env.data_root / "settings.json"
    original_mtime = settings_path.stat().st_mtime_ns
    original_text = settings_path.read_text()

    setup_env.prompts.extend([
        "openai",                                                              # provider
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",        # endpoint
        "${QWEN_KEY}",                                                         # auth_key (env ref unchanged)
        "text-embedding-v4",                                                   # model (dim 1024 unchanged)
        "",                                                                    # port (default)
        # wizard short-circuits — no start-server prompt
    ])

    result = setup_env.runner.invoke(setup_env.main, ["setup"])

    assert result.exit_code == 0, (result.stdout, result.exception)
    # File untouched
    assert settings_path.stat().st_mtime_ns == original_mtime
    assert settings_path.read_text() == original_text
    assert "nothing" in result.stdout.lower() and "unchanged" in result.stdout.lower()
    # 即便 settings 没变，probe 也应跑过（健康检查语义）
    assert "embedding verified" in setup_env.stderr()
