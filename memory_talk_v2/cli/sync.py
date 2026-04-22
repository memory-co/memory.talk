"""CLI: sync — iterate platform adapter and POST each session to /v2/sessions."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import click

from memory_talk_v2.adapters import get_adapter
from memory_talk_v2.cli._http import ApiError, api
from memory_talk_v2.config import Config


@click.command("sync")
@click.option("--source", default="claude-code", show_default=True,
              help="Platform adapter name")
@click.option("--platform-root", type=click.Path(), default=None,
              help="Override platform root path (default: adapter default)")
@click.option("--data-root", type=click.Path(), default=None)
def sync(source: str, platform_root: str | None, data_root: str | None) -> None:
    """Discover and ingest sessions from a platform source."""
    cfg = Config(data_root) if data_root else Config()
    try:
        adapter = get_adapter(source)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}, ensure_ascii=False))
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

    click.echo(json.dumps({"status": "ok", **counts, "errors": errors}, ensure_ascii=False))
