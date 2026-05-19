"""CLI: ``memory-talk sync`` — show backend sync status.

Sync is enabled/disabled via ``settings.json`` (``sync.enabled``) and
asked during ``memory-talk setup``. There is no longer a CLI ``start`` /
``stop`` — the watcher follows the config flag on every server
(re)start.
"""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_sync_status
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("sync")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
@click.option("--limit", type=int, default=5,
              help="Recent-events tail size (default 5)")
def sync(json_out: bool, limit: int) -> None:
    """Show backend sync status."""
    cfg = Config()
    try:
        result = api("GET", "/v3/sync/status", cfg, params={"limit": str(limit)})
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
        emit_md(fmt_sync_status(result))
