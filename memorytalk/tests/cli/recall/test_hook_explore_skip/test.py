"""recall --hook silently skips when payload.cwd is the configured explore.cwd.

Drives the real CLI via Click's CliRunner and pipes a UserPromptSubmit
payload through stdin. Verifies:
  - explore cwd → empty additionalContext (no API call attempted)
  - non-explore cwd → falls through to recall API (we monkeypatch the
    HTTP layer to capture / return canned data)
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from memorytalk.cli import _http, main
from memorytalk.config import Config


@pytest.fixture
def hook_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    data_root = tmp_path / ".memory-talk"
    data_root.mkdir()
    (data_root / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))
    explore_cwd = tmp_path / ".memory-talk" / "explore"
    explore_cwd.mkdir(parents=True)
    work_cwd = tmp_path / "work"
    work_cwd.mkdir()

    class Env:
        pass

    e = Env()
    e.runner = CliRunner()
    e.data_root = data_root
    e.explore_cwd = explore_cwd
    e.work_cwd = work_cwd
    e.config = Config(data_root)
    yield e


def _invoke_hook(runner: CliRunner, data_root: Path, payload: dict) -> tuple[int, str]:
    result = runner.invoke(
        main, ["recall", "--hook", "--data-root", str(data_root)],
        input=json.dumps(payload),
    )
    return result.exit_code, result.stdout


def test_hook_skips_when_cwd_is_explore_cwd(hook_env, monkeypatch):
    api_called = {"count": 0}

    def boom(*args, **kwargs):  # pragma: no cover — should not be called
        api_called["count"] += 1
        raise AssertionError("recall API should not be invoked from explore cwd")

    monkeypatch.setattr(_http, "api", boom)

    code, out = _invoke_hook(hook_env.runner, hook_env.data_root, {
        "session_id": "abc",
        "prompt": "what was that decision",
        "cwd": str(hook_env.explore_cwd),
    })
    assert code == 0
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["additionalContext"] == ""
    assert api_called["count"] == 0


def test_hook_passes_through_for_non_explore_cwd(hook_env, monkeypatch):
    """In a normal work cwd, recall API IS invoked."""
    captured = {"called": False}

    def fake_api(method, path, cfg, **kwargs):
        captured["called"] = True
        captured["body"] = kwargs.get("json_body")
        # Return a recall response shape that fmt_recall can render
        return {"recalled": [{"card_id": "card_x", "summary": "y"}]}

    monkeypatch.setattr("memorytalk.cli.recall.api", fake_api)

    code, out = _invoke_hook(hook_env.runner, hook_env.data_root, {
        "session_id": "abc",
        "prompt": "q",
        "cwd": str(hook_env.work_cwd),
    })
    assert code == 0
    assert captured["called"] is True
    payload = json.loads(out)
    assert "memory-talk view card_x" in payload["hookSpecificOutput"]["additionalContext"]


def test_hook_passes_through_when_payload_lacks_cwd(hook_env, monkeypatch):
    """Defensive: if Claude Code ever drops the cwd field, don't suppress."""
    called = {"n": 0}
    monkeypatch.setattr(
        "memorytalk.cli.recall.api",
        lambda *a, **kw: (called.__setitem__("n", called["n"] + 1) or {"recalled": []}),
    )
    code, out = _invoke_hook(hook_env.runner, hook_env.data_root, {
        "session_id": "abc",
        "prompt": "q",
    })
    assert code == 0
    assert called["n"] == 1
