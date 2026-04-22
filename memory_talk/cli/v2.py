"""v2 CLI — Click commands for memory-talk v2.

Currently only the `server` group is wired. `search`, `view`, `log`,
`card`, `tag`, `link`, `sync`, `rebuild` land in follow-up plans.
"""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time

import click
import httpx

from memory_talk.config import Config


__all__ = ["main"]


def _api(method: str, path: str, cfg: Config, **kwargs) -> dict:
    url = f"http://127.0.0.1:{cfg.settings.server.port}{path}"
    resp = httpx.request(method, url, timeout=30.0, **kwargs)
    resp.raise_for_status()
    return resp.json()


@click.group()
def main() -> None:
    """memory-talk v2 CLI."""


@main.group()
def server() -> None:
    """Manage the local API server."""


@server.command("start")
@click.option("--data-root", type=click.Path(), default=None)
def server_start(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    cfg.ensure_dirs()
    if cfg.pid_path.exists():
        pid = int(cfg.pid_path.read_text().strip())
        try:
            os.kill(pid, 0)
            click.echo(json.dumps({"status": "already_running", "pid": pid, "port": cfg.settings.server.port}))
            return
        except ProcessLookupError:
            cfg.pid_path.unlink()
    env = os.environ.copy()
    if data_root:
        env["MEMORY_TALK_DATA_ROOT"] = str(cfg.data_root)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "memory_talk.api:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(cfg.settings.server.port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True,
    )
    time.sleep(1.0)
    if proc.poll() is not None:
        err = (proc.stderr.read() or b"").decode(errors="replace")
        click.echo(json.dumps({"status": "failed", "exit_code": proc.returncode, "error": err.strip()}))
        sys.exit(1)
    cfg.pid_path.write_text(str(proc.pid))
    click.echo(json.dumps({"status": "started", "pid": proc.pid, "port": cfg.settings.server.port}))


@server.command("stop")
@click.option("--data-root", type=click.Path(), default=None)
def server_stop(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    if not cfg.pid_path.exists():
        click.echo(json.dumps({"status": "not_running"}))
        return
    pid = int(cfg.pid_path.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    cfg.pid_path.unlink(missing_ok=True)
    click.echo(json.dumps({"status": "stopped", "pid": pid}))


@server.command("status")
@click.option("--data-root", type=click.Path(), default=None)
def server_status(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    try:
        data = _api("GET", "/v2/status", cfg)
        click.echo(json.dumps(data))
    except Exception:
        click.echo(json.dumps({
            "data_root": str(cfg.data_root),
            "settings_path": str(cfg.settings_path),
            "status": "not_running",
        }))
