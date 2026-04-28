"""CLI: search <query> [--where DSL] [--top-k N] [--json] → POST /v2/search."""
from __future__ import annotations
import sys

import click

from memory_talk_v2.cli._format import fmt_error, fmt_search
from memory_talk_v2.cli._http import ApiError, api, extract_error_message
from memory_talk_v2.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memory_talk_v2.config import Config


@click.command("search")
@click.argument("query")
@click.option("--where", default=None, help="Metadata DSL filter")
@click.option("--top-k", type=int, default=None, help="Top-k per bucket")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def search(query: str, where: str | None, top_k: int | None,
           data_root: str | None, json_out: bool) -> None:
    """Hybrid search over cards + sessions."""
    cfg = Config(data_root) if data_root else Config()
    body = {"query": query}
    if where:
        body["where"] = where
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v2/search", cfg, json_body=body, timeout=60.0)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_search(result))
