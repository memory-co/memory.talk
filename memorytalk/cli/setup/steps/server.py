"""Wizard step: start / restart the server based on prior state.

Branches on (is_running, settings_changed):
- running + changed → ask whether to restart, do stop+start
- running + unchanged → leave it
- not running → ask whether to start

Both questions are arrow-key selects (yes/no with descriptions) instead
of typed y/n, matching the rest of the wizard's feel.
"""
from __future__ import annotations

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md_err
from memorytalk.cli.server import pid_alive, start_server_proc, stop_server_proc
from memorytalk.config import Config

from .. import _prompt
from .._io import err_console


_YES_NO_RESTART = [
    _prompt.Option("yes", description="stop the running server and start a fresh one with the new settings"),
    _prompt.Option("no",  description="leave the running server alone (settings will only apply on next restart)"),
]

_YES_NO_START = [
    _prompt.Option("yes", description="start the memory-talk server in the background now"),
    _prompt.Option("no",  description="skip — start it manually later with `memory-talk server start`"),
]


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
        choice = _prompt.select(
            f"server is running (pid {pid}). settings changed — restart now?",
            _YES_NO_RESTART, default="yes",
        )
        if choice == "no":
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

    choice = _prompt.select("start server now?", _YES_NO_START, default="yes")
    if choice == "yes":
        start_payload = start_server_proc(cfg)
        if start_payload.get("status") == "failed":
            emit_md_err(fmt_error(f"server failed to start: {start_payload.get('error')}"))
        return start_payload
    return {"status": "not_started"}
