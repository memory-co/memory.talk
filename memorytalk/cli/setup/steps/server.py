"""Wizard step: start / restart the server based on prior state.

Branches on (is_running, settings_changed):
- running + changed → ask to restart, do stop+start
- running + unchanged → leave it
- not running → ask to start

The actual subprocess management lives in ``memorytalk.cli.server``;
this step just orchestrates the prompts and reports back what happened
(the summary uses the returned dict).
"""
from __future__ import annotations

from rich.prompt import Confirm

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md_err
from memorytalk.cli.server import pid_alive, start_server_proc, stop_server_proc
from memorytalk.config import Config

from .._io import err_console


def _step_server(cfg: Config, settings_changed: bool) -> dict | None:
    is_running = False
    pid = 0
    if cfg.pid_path.exists():
        try:
            pid = int(cfg.pid_path.read_text().strip())
            is_running = pid_alive(pid)
        except ValueError:
            cfg.pid_path.unlink(missing_ok=True)

    if is_running and settings_changed:
        if not Confirm.ask(
            f"server is running (pid {pid}). settings changed — restart now?",
            console=err_console, default=True,
        ):
            err_console.print(
                "[yellow]warning:[/yellow] settings written but old server is still using old config. "
                "Run `memory-talk server stop && memory-talk server start` when ready."
            )
            return {"status": "running_stale", "pid": pid}
        stop_payload = stop_server_proc(cfg)
        err_console.print(f"[dim]stopped pid {stop_payload.get('pid')}[/dim]")
        start_payload = start_server_proc(cfg)
        if start_payload.get("status") == "failed":
            emit_md_err(fmt_error(f"server failed to start: {start_payload.get('error')}"))
            return start_payload
        return {**start_payload, "restarted": True}

    if is_running and not settings_changed:
        return {"status": "running", "pid": pid}

    if Confirm.ask("start server now?", console=err_console, default=True):
        start_payload = start_server_proc(cfg)
        if start_payload.get("status") == "failed":
            emit_md_err(fmt_error(f"server failed to start: {start_payload.get('error')}"))
        return start_payload
    return {"status": "not_started"}
