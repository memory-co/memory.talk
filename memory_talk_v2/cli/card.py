"""CLI: card <json> → POST /v2/cards."""
from __future__ import annotations
import json
import sys

import click

from memory_talk_v2.cli._http import ApiError, api
from memory_talk_v2.config import Config


@click.command("card")
@click.argument("body_json")
@click.option("--data-root", type=click.Path(), default=None)
def card(body_json: str, data_root: str | None) -> None:
    """Create a talk-card (inline JSON body for POST /v2/cards)."""
    cfg = Config(data_root) if data_root else Config()
    try:
        body = json.loads(body_json)
    except json.JSONDecodeError as e:
        click.echo(json.dumps({"error": f"invalid json: {e}"}, ensure_ascii=False))
        sys.exit(1)
    try:
        result = api("POST", "/v2/cards", cfg, json_body=body)
        click.echo(json.dumps(result, ensure_ascii=False))
    except ApiError as e:
        click.echo(json.dumps({"error": e.payload}, ensure_ascii=False))
        sys.exit(1)
