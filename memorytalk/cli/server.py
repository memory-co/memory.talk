"""CLI: server start / stop / status / logs [--json].

Lifecycle primitives (``start_server_proc`` / ``stop_server_proc`` /
``pid_alive``) are exported separately so other commands (notably
``memory-talk setup``) can reuse them without subprocess-ing themselves.
"""
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click

from memorytalk.cli._format import fmt_server_start, fmt_server_stop, fmt_status
from memorytalk.cli._http import ApiError, api
from memorytalk.cli._render import emit_json, emit_md
from memorytalk.config import Config


@click.group()
def server() -> None:
    """Manage the local API server."""


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _server_responsive(cfg: Config) -> bool:
    """HTTP-probe the server. ``pid_alive`` alone can't tell us whether
    the PID in ``server.pid`` is actually our daemon — the kernel may
    have recycled it to an unrelated process after a crash/reboot. A
    successful ``/v3/status`` call proves it really is memory-talk."""
    try:
        api("GET", "/v3/status", cfg, timeout=1.0)
        return True
    except Exception:
        return False


def start_server_proc(cfg: Config) -> dict:
    """Start the API server as a daemon. Returns one of:

        {"status": "started",         "pid": int, "port": int}
        {"status": "already_running", "pid": int, "port": int}
        {"status": "failed",          "exit_code": int, "error": str}
    """
    cfg.ensure_dirs()
    port = cfg.settings.server.port

    if cfg.pid_path.exists():
        try:
            pid = int(cfg.pid_path.read_text().strip())
        except ValueError:
            pid = 0
        if pid and pid_alive(pid) and _server_responsive(cfg):
            return {"status": "already_running", "pid": pid, "port": port}
        cfg.pid_path.unlink(missing_ok=True)
        cfg.port_path.unlink(missing_ok=True)

    env = os.environ.copy()
    env["MEMORY_TALK_DATA_ROOT"] = str(cfg.data_root)

    # Launch via the in-repo shim (``memorytalk/server.py``) instead of
    # uvicorn directly. The shim redirects OS-level stdout/stderr to
    # ``logs/server.log`` and configures Python ``logging`` with a
    # rotating file handler before uvicorn starts — so the daemon's
    # logs survive the parent CLI exiting.
    #
    # ``stderr=subprocess.PIPE`` is kept narrowly for the 1.2s failure
    # probe below: errors from interpreter startup or module-import
    # time happen before the shim's ``_redirect_os_fds_to`` runs, so
    # we still want to capture those into the failure payload. After
    # the shim reassigns fd 2, nothing else writes to the pipe.
    proc = subprocess.Popen(
        [sys.executable, "-m", "memorytalk.server"],
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
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def server_start(json_out: bool) -> None:
    cfg = Config()
    payload = start_server_proc(cfg)
    _emit(payload, json_out, fmt_server_start)
    if payload.get("status") == "failed":
        sys.exit(1)


@server.command("stop")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def server_stop(json_out: bool) -> None:
    cfg = Config()
    payload = stop_server_proc(cfg)
    _emit(payload, json_out, fmt_server_stop)


@server.command("status")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def server_status(json_out: bool) -> None:
    cfg = Config()
    try:
        payload = api("GET", "/v3/status", cfg)
    except (ApiError, Exception):
        # Anything that prevents us from reaching the server → not_running
        payload = {
            "status": "not_running",
            "data_root": str(cfg.data_root),
            "settings_path": str(cfg.settings_path),
        }
    _emit(payload, json_out, fmt_status)


def _tail_bytes(path: Path, n_lines: int) -> list[bytes]:
    """Return the last ``n_lines`` lines of ``path`` cheaply by reading
    backward in chunks. Bounded to the last 1 MB so we never load a
    huge log into memory."""
    cap = 1024 * 1024
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        read_size = min(size, cap)
        f.seek(size - read_size)
        chunk = f.read(read_size)
    lines = chunk.splitlines()
    return lines[-n_lines:]


@server.command("logs")
@click.option("-f", "--follow", is_flag=True, default=False,
              help="Stream new log lines as they're written (like tail -f)")
@click.option("-n", "--lines", type=int, default=100,
              help="Number of trailing lines to show first (default 100)")
def server_logs(follow: bool, lines: int) -> None:
    """Tail the daemon's log file (``~/.memory-talk/logs/server.log``)."""
    cfg = Config()
    log_path = cfg.logs_dir / "server.log"
    if not log_path.exists():
        click.echo("(no log file yet — has the server been started?)", err=True)
        sys.exit(1)

    for raw in _tail_bytes(log_path, lines):
        click.echo(raw.decode(errors="replace"))

    if not follow:
        return

    # ``tail -f`` loop. We don't track inode changes — if the file gets
    # rotated mid-follow we silently keep reading the rotated copy. The
    # user can rerun the command to pick up the live file again.
    with log_path.open("rb") as f:
        f.seek(0, 2)
        try:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                click.echo(line.decode(errors="replace").rstrip("\n"))
        except KeyboardInterrupt:
            pass
