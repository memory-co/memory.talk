"""First-install with openai provider — mocked HTTP probe."""
from __future__ import annotations
import json


def test_first_install_openai_writes_settings(setup_env):
    setup_env.mock_openai_probe(dim=1024)

    answers = "\n".join([
        "2",                  # install_mode: use current
        "openai",             # embedding provider
        "",                   # endpoint default
        "",                   # auth_env_key default
        "",                   # model default
        "",                   # dim default
        # vector / relation single-option steps don't prompt — no input consumed
        "",                   # port default
        "y",                  # start server
    ]) + "\n"

    result = setup_env.runner.invoke(
        setup_env.main,
        ["setup", "--data-root", str(setup_env.data_root)],
        input=answers,
    )

    assert result.exit_code == 0, (result.stdout, result.exception)

    settings_path = setup_env.data_root / "settings.json"
    assert settings_path.exists()
    data = json.loads(settings_path.read_text())
    assert data["embedding"]["provider"] == "openai"
    assert data["embedding"]["model"] == "text-embedding-v4"
    assert data["embedding"]["dim"] == 1024
    assert data["embedding"]["auth_env_key"] == "QWEN_KEY"
    assert data["server"]["port"] == 7788
    assert data["vector"]["provider"] == "lancedb"
    assert data["relation"]["provider"] == "sqlite"

    # data subdirs created
    for sub in ("sessions", "cards", "links", "vectors", "logs/search"):
        assert (setup_env.data_root / sub).exists()

    # markdown summary has the expected lines
    assert "# setup · **ok**" in result.stdout
    assert "openai" in result.stdout
    assert "text-embedding-v4" in result.stdout
