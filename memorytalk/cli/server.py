"""CLI: server start / stop / status [--json].

The lifecycle primitives (`start_server_proc` / `stop_server_proc` /
`pid_alive`) are exported separately so other commands (notably
`memory-talk setup`) can reuse them without subprocess-ing themselves.
"""
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time

import click

from memorytalk.cli._format import (
    fmt_server_start, fmt_server_stop, fmt_status,
)
from memorytalk.cli import _http
from memorytalk.cli._http import api
from memorytalk.cli._render import emit_json, emit_md
from memorytalk.config import Config, ConfigValidationError


@click.group()
def server() -> None:
    """Manage the local API server."""


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def start_server_proc(cfg: Config) -> dict:
    """Start the API server as a daemon. Returns one of:

      {"status": "started",         "pid": <int>, "port": <int>}
      {"status": "already_running", "pid": <int>, "port": <int>}
      {"status": "failed",          "exit_code": <int>, "error": <str>}
    """
    cfg.ensure_dirs()
    port = cfg.settings.server.port

    if cfg.pid_path.exists():
        try:
            pid = int(cfg.pid_path.read_text().strip())
        except ValueError:
            pid = 0
        if pid and pid_alive(pid):
            return {"status": "already_running", "pid": pid, "port": port}
        cfg.pid_path.unlink(missing_ok=True)

    env = os.environ.copy()
    env["MEMORY_TALK_DATA_ROOT"] = str(cfg.data_root)

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "memorytalk.api:app",
            "--host", "127.0.0.1",
            "--port", str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    # Give it a moment; if it dies on startup checks we'll know quickly.
    time.sleep(1.2)
    if proc.poll() is not None:
        err = (proc.stderr.read() or b"").decode(errors="replace") if proc.stderr else ""
        return {"status": "failed", "exit_code": proc.returncode, "error": err.strip()}

    cfg.pid_path.write_text(str(proc.pid))
    cfg.port_path.write_text(str(port))
    return {"status": "started", "pid": proc.pid, "port": port}


def stop_server_proc(cfg: Config) -> dict:
    """SIGTERM the daemon and clean up the pid file. Returns:

      {"status": "stopped",     "pid": <int>}
      {"status": "not_running"}
    """
    if not cfg.pid_path.exists():
        return {"status": "not_running"}
    try:
        pid = int(cfg.pid_path.read_text().strip())
    except ValueError:
        cfg.pid_path.unlink(missing_ok=True)
        return {"status": "not_running"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    cfg.pid_path.unlink(missing_ok=True)
    cfg.port_path.unlink(missing_ok=True)
    return {"status": "stopped", "pid": pid}


def _emit(payload: dict, json_out: bool, md_formatter) -> None:
    if json_out:
        emit_json(payload)
    else:
        emit_md(md_formatter(payload))


@server.command("start")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def server_start(data_root: str | None, json_out: bool) -> None:
    cfg = Config(data_root) if data_root else Config()
    payload = start_server_proc(cfg)
    _emit(payload, json_out, fmt_server_start)
    if payload.get("status") == "failed":
        sys.exit(1)


@server.command("stop")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def server_stop(data_root: str | None, json_out: bool) -> None:
    cfg = Config(data_root) if data_root else Config()
    payload = stop_server_proc(cfg)
    _emit(payload, json_out, fmt_server_stop)


def _daemon_alive(cfg: Config) -> bool:
    """True iff the pid file points at a live process. Pid is the source
    of truth for 'should be alive'; HTTP is the source of truth for
    'actually serving' — `server status` checks both."""
    if not cfg.pid_path.exists():
        return False
    try:
        pid = int(cfg.pid_path.read_text().strip())
    except ValueError:
        return False
    return pid_alive(pid)


@server.command("status")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def server_status(data_root: str | None, json_out: bool) -> None:
    cfg = Config(data_root) if data_root else Config()

    not_running = {
        "data_root": str(cfg.data_root),
        "settings_path": str(cfg.settings_path),
        "status": "not_running",
    }

    # In tests, ``_make_client`` is monkeypatched to an ASGI transport,
    # so there is no real daemon and no pid file. Skip the local-process
    # liveness check on that path — production calls always leave
    # ``_make_client`` as None.
    asgi_test_mode = _http._make_client is not None
    if not asgi_test_mode and not _daemon_alive(cfg):
        data = not_running
    else:
        # Daemon process is alive — try to resolve its port and probe
        # /v2/status. resolve_port() prefers the port file and only
        # falls back to settings.json, so a broken settings.json no
        # longer hides a live server.
        try:
            data = api("GET", "/v2/status", cfg, timeout=3.0)
        except ConfigValidationError as e:
            # Pid alive, no port file, and settings.json won't render.
            # Surface the real error rather than lying about the daemon
            # state — masking as 'not_running' here is what made the
            # original bug so confusing to diagnose.
            emit_md(f"# memory-talk · **error**\n\n{e}\n")
            sys.exit(1)
        except Exception:
            # Pid alive but HTTP didn't answer — daemon is wedged or
            # mid-shutdown. Surface as not_running.
            data = not_running

    if json_out:
        emit_json(data)
    else:
        emit_md(fmt_status(data))
