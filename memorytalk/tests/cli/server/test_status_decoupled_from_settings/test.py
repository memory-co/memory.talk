"""CLI commands must not depend on settings.json being renderable when
the daemon is already running.

Regression: previously every CLI command (status, sync, search, recall,
…) built its HTTP client by reading ``cfg.settings.server.port``. If
settings.json contained a ${VAR} reference to an unset env var (or any
other ConfigValidationError trigger), the load would raise — and
``server status`` swallowed that as ``not_running`` while every other
command crashed with a stack trace. Both modes were misleading because
the daemon itself was fine: env vars get rendered at server-startup
time, not on every CLI request.

Fix: ``server start`` now writes ``server.port`` next to ``server.pid``,
and ``cli/_http.resolve_port()`` reads the port file first, only
falling back to settings.json if the file is missing. Every CLI command
inherits the fix because they all go through ``cli/_http.api()``.
"""
from __future__ import annotations
import json

from memorytalk.cli import main


def _invoke(server_env, *args):
    return server_env.runner.invoke(
        main,
        list(args) + ["--data-root", str(server_env.data_root), "--json"],
    )


async def test_cli_works_when_settings_env_var_unset(server_env, monkeypatch):
    # Start the server with an env var set so it can boot...
    monkeypatch.setenv("STATUS_DECOUPLE_KEY", "sk-fake-but-present")
    server_env.write_settings({
        "embedding": {
            "provider": "dummy",
            "model": "ignored",
            "auth_key": "${STATUS_DECOUPLE_KEY}",
        },
    })

    summary = server_env.start()
    assert summary["status"] == "started"
    server_env.wait_ready()

    # ...then unset the env var. Re-loading settings would now raise
    # ConfigValidationError.
    monkeypatch.delenv("STATUS_DECOUPLE_KEY", raising=False)

    # 1. `server status` must still report 'running' — the original
    #    broken case. Daemon and HTTP endpoint are unaffected.
    r = _invoke(server_env, "server", "status")
    assert r.exit_code == 0, f"status failed: stdout={r.stdout!r}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "running", (
        f"status should be 'running' even when settings env var is missing, "
        f"got {payload}"
    )

    # 2. A regular CLI command (here: `view` on a missing id) must hit
    #    the server and get a 404 back — proving the HTTP plumbing
    #    works. Before the fix it crashed with ConfigValidationError
    #    instead of ever reaching the daemon.
    r = _invoke(server_env, "view", "sess_does-not-exist")
    assert "ConfigValidationError" not in (r.stderr or ""), (
        f"CLI command crashed on settings load instead of reaching the "
        f"server. stderr={r.stderr!r}"
    )
    # Exit code may be non-zero (id doesn't exist) but stderr should be a
    # clean API error from the server, not a Python traceback.
    assert "Traceback" not in (r.stderr or ""), (
        f"unexpected traceback: {r.stderr!r}"
    )
