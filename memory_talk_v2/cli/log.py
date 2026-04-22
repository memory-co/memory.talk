"""CLI: log <id> → POST /v2/log."""
from __future__ import annotations
import json
import sys

import click

from memory_talk_v2.cli._http import ApiError, api
from memory_talk_v2.config import Config


@click.command("log")
@click.argument("object_id")
@click.option("--data-root", type=click.Path(), default=None)
def log(object_id: str, data_root: str | None) -> None:
    """Show lifecycle events for a card or session."""
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("POST", "/v2/log", cfg, json_body={"id": object_id})
        click.echo(json.dumps(result, ensure_ascii=False))
    except ApiError as e:
        click.echo(json.dumps({"error": e.payload}, ensure_ascii=False))
        sys.exit(1)
