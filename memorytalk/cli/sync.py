"""CLI: sync [--json] — iterate platform adapter and POST each session to /v2/sessions."""
from __future__ import annotations
import sys
from pathlib import Path

import click

from memorytalk.adapters import get_adapter
from memorytalk.cli._format import fmt_error, fmt_sync
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("sync")
@click.option("--source", default="claude-code", show_default=True,
              help="Platform adapter name")
@click.option("--platform-root", type=click.Path(), default=None,
              help="Override platform root path (default: adapter default)")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def sync(source: str, platform_root: str | None, data_root: str | None, json_out: bool) -> None:
    """Discover and ingest sessions from a platform source."""
    cfg = Config(data_root) if data_root else Config()
    try:
        adapter = get_adapter(source)
    except ValueError as e:
        if json_out:
            emit_json_err(str(e))
        else:
            emit_md_err(fmt_error(str(e)))
        sys.exit(1)

    counts = {"imported": 0, "appended": 0, "skipped": 0, "partial_append": 0}
    errors: list[dict] = []

    root_path = Path(platform_root) if platform_root else None
    for payload in adapter.iter_sessions(root_path):
        try:
            result = api("POST", "/v2/sessions", cfg, json_body=payload, timeout=60.0)
            action = result.get("action")
            if action in counts:
                counts[action] += 1
        except ApiError as e:
            errors.append({"session_id": payload.get("session_id"), "error": e.payload})

    summary = {"status": "ok", **counts, "errors": errors}
    if json_out:
        emit_json(summary)
    else:
        # The Markdown formatter expects a flat 'errors' count; keep both views.
        md_payload = {**summary, "errors": len(errors)}
        emit_md(fmt_sync(md_payload))
        for err in errors:
            emit_md_err(fmt_error(
                f"{err.get('session_id', '?')}: {extract_error_message(err.get('error'))}"
            ))
