"""First-install with local provider — embedder probe stubbed out."""
from __future__ import annotations
import json


async def _noop_validate(cfg):
    return None


def test_first_install_local_writes_settings(setup_env, monkeypatch):
    from memorytalk.cli.setup.steps import embedding as embedding_step
    monkeypatch.setattr(embedding_step, "validate_embedder", _noop_validate)

    setup_env.prompts.extend([
        "local",                # embedding provider select
        "all-MiniLM-L6-v2",     # model select (dim 384 auto-derived)
        "",                     # port text → default 7788
        "no",                   # start server select → don't start
    ])

    result = setup_env.runner.invoke(setup_env.main, ["setup"])

    assert result.exit_code == 0, (result.stdout, result.exception)

    data = json.loads((setup_env.data_root / "settings.json").read_text())
    assert data["embedding"]["provider"] == "local"
    assert data["embedding"]["model"] == "all-MiniLM-L6-v2"
    assert data["embedding"]["dim"] == 384
    assert data["embedding"]["endpoint"] is None
    assert data["embedding"]["auth_env_key"] is None

    assert "not_started" in result.stdout
