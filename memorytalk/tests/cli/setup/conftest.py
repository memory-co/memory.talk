"""Shared fixtures for in-process `memory-talk setup` tests.

Setup's first action is to bootstrap a venv at ``~/.memory-talk/.venv``
and re-exec into it. For the **wizard** tests we don't want either of
those to actually happen (real venv creation is slow + would write to
the dev's real home, and os.execv would replace pytest itself). So this
fixture stubs them out, plus the server lifecycle and the PATH takeover
(stubbed to a no-op; the takeover logic has its own dedicated test).

Wizard answers go through the ``memorytalk.cli.console`` shim (which
wraps questionary). The fixture exposes a ``prompts`` list
on the env object — tests append answers in call order, then invoke the
CLI. Each answer must match the call site:

- ``select`` → the chosen Option's ``value`` (string)
- ``text``   → string; empty string falls back to the call's default
- ``confirm``→ bool

If a test runs out of answers before the wizard runs out of prompts,
the fixture raises so the failure is obvious. Same goes for type mismatch
(e.g. feeding a bool to a ``select``).

The bootstrap+execv path itself is exercised by a separate scenario,
``tests/cli/setup/test_bootstrap_real_venv``, which spins up a real
outer venv via subprocess and goes through the shim's non-TTY fallback.
"""
from __future__ import annotations
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from memorytalk.cli import main


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    runner = CliRunner()

    class Env:
        pass

    env = Env()
    env.fake_home = fake_home
    env.data_root = fake_home / ".memory-talk"   # Config(_data_root()) default
    env.runner = runner
    env.main = main
    env.prompts: list = []        # tests .extend(...) with canned answers

    # err_console captured a real sys.stderr at module-import time, so
    # CliRunner's stderr redirect and pytest's capfd both miss its output.
    # Redirect the Console's file at the instance level to a StringIO the
    # test can read via env.stderr.
    from memorytalk.cli.console import err_console
    env.stderr_buf = io.StringIO()
    monkeypatch.setattr(err_console, "file", env.stderr_buf)
    env.stderr = lambda: env.stderr_buf.getvalue()

    from memorytalk.cli import console as console_mod
    from memorytalk.cli import setup as setup_pkg
    from memorytalk.cli.setup.steps import server as server_step

    # Pretend we're already inside the venv → skip the bootstrap branch
    # entirely (no answer needed in env.prompts for it). Tests that want
    # to exercise the bootstrap prompt re-monkeypatch this to False.
    monkeypatch.setattr(setup_pkg, "_already_in_venv", lambda: True)
    monkeypatch.setattr(setup_pkg, "_bootstrap_venv", lambda: None)
    monkeypatch.setattr(setup_pkg, "_reexec_into_venv", lambda: None)

    # Server lifecycle is patched on its call-site module.
    monkeypatch.setattr(
        server_step, "start_server_proc",
        lambda cfg: {"status": "started", "pid": 99999, "port": cfg.settings.server.port},
    )
    monkeypatch.setattr(
        server_step, "stop_server_proc",
        lambda cfg: {"status": "stopped", "pid": 99999},
    )
    monkeypatch.setattr(server_step, "pid_alive", lambda pid: False)

    # Skip the PATH takeover — `_step_path_takeover` is called from
    # the setup entry point right after the venv decision. The dedicated
    # takeover test exercises it directly.
    monkeypatch.setattr(
        setup_pkg, "_step_path_takeover",
        lambda *a, **kw: {"target": str(a[0]) if a else "", "actions": []},
    )

    # ----- prompt shim: drain env.prompts in call order -----

    def _next(kind: str, label: str):
        if not env.prompts:
            raise AssertionError(
                f"{kind}({label!r}) — no canned answer left in env.prompts"
            )
        return env.prompts.pop(0)

    def _select(label, options, default=None):
        ans = _next("select", label)
        valid = [o.value for o in options]
        if ans not in valid:
            raise AssertionError(
                f"select({label!r}) — answer {ans!r} not in options {valid!r}"
            )
        return ans

    def _text(label, default="", validate=None):
        ans = _next("text", label)
        result = default if ans in (None, "") else ans
        if validate is not None:
            v = validate(result)
            if v is not True:
                raise AssertionError(f"text({label!r}) failed validation: {v}")
        return result

    def _confirm(label, default=True):
        ans = _next("confirm", label)
        if not isinstance(ans, bool):
            raise AssertionError(
                f"confirm({label!r}) — expected bool, got {ans!r}"
            )
        return ans

    monkeypatch.setattr(console_mod, "select", _select)
    monkeypatch.setattr(console_mod, "text", _text)
    monkeypatch.setattr(console_mod, "confirm", _confirm)

    def mock_openai_probe(dim: int = 1024) -> None:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * dim}]}
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=resp)
        from memorytalk.provider import embedding as emb_mod
        monkeypatch.setattr(emb_mod.httpx, "AsyncClient", lambda *a, **kw: client)

    env.mock_openai_probe = mock_openai_probe
    return env
