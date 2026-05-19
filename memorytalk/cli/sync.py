"""CLI: sync start / stop / status [--json]."""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import (
    fmt_error, fmt_sync_start, fmt_sync_status, fmt_sync_stop,
)
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.group()
def sync() -> None:
    """Backend watchdog control plane (start / stop / status)."""


def _call(method: str, path: str, json_out: bool, fmt, body: dict | None = None,
          params: dict | None = None) -> dict | None:
    cfg = Config()
    try:
        result = api(method, path, cfg, json_body=body, params=params)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)
    except Exception as e:
        if json_out:
            emit_json_err(str(e))
        else:
            emit_md_err(fmt_error(f"cannot reach server: {e}"))
        sys.exit(1)
    if json_out:
        emit_json(result)
    else:
        emit_md(fmt(result))
    return result


@sync.command("start")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def sync_start(json_out: bool) -> None:
    """Start the backend watcher (runs an initial backfill, then watches)."""
    _call("POST", "/v3/sync/start", json_out, fmt_sync_start)


@sync.command("stop")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def sync_stop(json_out: bool) -> None:
    """Stop the backend watcher (already-ingested data is untouched)."""
    _call("POST", "/v3/sync/stop", json_out, fmt_sync_stop)


@sync.command("status")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
@click.option("--limit", type=int, default=5,
              help="Recent-events tail size (default 5)")
def sync_status(json_out: bool, limit: int) -> None:
    """Show watcher state + accumulated totals + recent events."""
    _call("GET", "/v3/sync/status", json_out, fmt_sync_status,
          params={"limit": str(limit)})
