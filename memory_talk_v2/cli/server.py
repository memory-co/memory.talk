"""CLI: server start / stop / status."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click

from memory_talk_v2.cli._http import api, ApiError
from memory_talk_v2.config import Config


@click.group()
def server() -> None:
    """Manage the local API server."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


@server.command("start")
@click.option("--data-root", type=click.Path(), default=None)
def server_start(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    cfg.ensure_dirs()
    port = cfg.settings.server.port

    if cfg.pid_path.exists():
        try:
            pid = int(cfg.pid_path.read_text().strip())
        except ValueError:
            pid = 0
        if pid and _pid_alive(pid):
            click.echo(json.dumps({"status": "already_running", "pid": pid, "port": port}, ensure_ascii=False))
            return
        cfg.pid_path.unlink(missing_ok=True)

    env = os.environ.copy()
    if data_root:
        env["MEMORY_TALK_DATA_ROOT"] = str(cfg.data_root)

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "memory_talk_v2.api:app",
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
        click.echo(json.dumps({
            "status": "failed",
            "exit_code": proc.returncode,
            "error": err.strip(),
        }, ensure_ascii=False))
        sys.exit(1)

    cfg.pid_path.write_text(str(proc.pid))
    click.echo(json.dumps({"status": "started", "pid": proc.pid, "port": port}, ensure_ascii=False))


@server.command("stop")
@click.option("--data-root", type=click.Path(), default=None)
def server_stop(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    if not cfg.pid_path.exists():
        click.echo(json.dumps({"status": "not_running"}, ensure_ascii=False))
        return
    try:
        pid = int(cfg.pid_path.read_text().strip())
    except ValueError:
        cfg.pid_path.unlink(missing_ok=True)
        click.echo(json.dumps({"status": "not_running"}, ensure_ascii=False))
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    cfg.pid_path.unlink(missing_ok=True)
    click.echo(json.dumps({"status": "stopped", "pid": pid}, ensure_ascii=False))


@server.command("status")
@click.option("--data-root", type=click.Path(), default=None)
def server_status(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    try:
        data = api("GET", "/v2/status", cfg, timeout=3.0)
        click.echo(json.dumps(data, ensure_ascii=False))
    except Exception:
        click.echo(json.dumps({
            "data_root": str(cfg.data_root),
            "settings_path": str(cfg.settings_path),
            "status": "not_running",
        }, ensure_ascii=False))
