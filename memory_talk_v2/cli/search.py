"""CLI: search <query> [--where DSL] [--top-k N] → POST /v2/search."""
from __future__ import annotations
import json
import sys

import click

from memory_talk_v2.cli._http import ApiError, api
from memory_talk_v2.config import Config


@click.command("search")
@click.argument("query")
@click.option("--where", default=None, help="Metadata DSL filter")
@click.option("--top-k", type=int, default=None, help="Top-k per bucket")
@click.option("--data-root", type=click.Path(), default=None)
def search(query: str, where: str | None, top_k: int | None, data_root: str | None) -> None:
    """Hybrid search over cards + sessions."""
    cfg = Config(data_root) if data_root else Config()
    body = {"query": query}
    if where:
        body["where"] = where
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v2/search", cfg, json_body=body, timeout=60.0)
        click.echo(json.dumps(result, ensure_ascii=False))
    except ApiError as e:
        click.echo(json.dumps({"error": e.payload}, ensure_ascii=False))
        sys.exit(1)
