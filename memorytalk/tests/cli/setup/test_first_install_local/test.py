"""First-install with local provider — embedder probe stubbed out."""
from __future__ import annotations
import json


async def _noop_validate(cfg):
    return None


def test_first_install_local_writes_settings(setup_env, monkeypatch):
    from memorytalk.cli import setup as setup_module
    monkeypatch.setattr(setup_module, "validate_embedder", _noop_validate)

    answers = "\n".join([
        "local",    # embedding provider
        "",         # model default
        "",         # dim default
        # vector / relation auto-pick — no input consumed
        "",         # port default
        "n",        # don't start server
    ]) + "\n"

    result = setup_env.runner.invoke(setup_env.main, ["setup"], input=answers)

    assert result.exit_code == 0, (result.stdout, result.exception)

    data = json.loads((setup_env.data_root / "settings.json").read_text())
    assert data["embedding"]["provider"] == "local"
    assert data["embedding"]["model"] == "all-MiniLM-L6-v2"
    assert data["embedding"]["dim"] == 384
    assert data["embedding"]["endpoint"] is None
    assert data["embedding"]["auth_env_key"] is None

    assert "not_started" in result.stdout
