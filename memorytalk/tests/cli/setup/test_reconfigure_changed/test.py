"""Reconfigure path with one field changed — atomic rewrite, summary tracks the diff."""
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
            "auth_env_key": "QWEN_KEY",
            "model": "text-embedding-v4",
            "dim": 1024,
            "timeout": 30.0,
        },
    }, indent=2))


def test_reconfigure_changed_writes_new_value(setup_env):
    setup_env.mock_openai_probe(dim=1024)
    _seed_settings(setup_env.data_root)

    answers = "\n".join([
        "2",                       # install_mode
        "",                        # provider default (openai)
        "",                        # endpoint default
        "",                        # auth_env_key default
        "text-embedding-v3",       # NEW model
        "",                        # dim default
        # vector / relation auto-pick — no input consumed
        "",                        # port default
        "n",                       # don't start server
    ]) + "\n"

    result = setup_env.runner.invoke(
        setup_env.main,
        ["setup", "--data-root", str(setup_env.data_root)],
        input=answers,
    )

    assert result.exit_code == 0, (result.stdout, result.exception)
    data = json.loads((setup_env.data_root / "settings.json").read_text())
    assert data["embedding"]["model"] == "text-embedding-v3"

    # Summary lists what changed
    assert "embedding.model" in result.stdout
