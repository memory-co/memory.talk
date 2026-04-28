"""First-install with local provider — embedder probe stubbed out."""
from __future__ import annotations
import json


async def _noop_validate(cfg):
    return None


def test_first_install_local_writes_settings(setup_env, monkeypatch):
    # Stub validate_embedder so the local branch doesn't try to download
    # all-MiniLM-L6-v2 over the network during tests.
    from memory_talk_v2.cli import setup as setup_module
    monkeypatch.setattr(setup_module, "validate_embedder", _noop_validate)

    answers = "\n".join([
        "2",        # install_mode: use current
        "local",    # embedding provider
        "",         # model default
        "",         # dim default
        # vector / relation auto-pick — no input consumed
        "",         # port default
        "n",        # don't start server
    ]) + "\n"

    result = setup_env.runner.invoke(
        setup_env.main,
        ["setup", "--data-root", str(setup_env.data_root)],
        input=answers,
    )

    assert result.exit_code == 0, (result.stdout, result.exception)

    data = json.loads((setup_env.data_root / "settings.json").read_text())
    assert data["embedding"]["provider"] == "local"
    assert data["embedding"]["model"] == "all-MiniLM-L6-v2"
    assert data["embedding"]["dim"] == 384
    assert data["embedding"]["endpoint"] is None
    assert data["embedding"]["auth_env_key"] is None

    # User declined to start the server.
    assert "not_started" in result.stdout
