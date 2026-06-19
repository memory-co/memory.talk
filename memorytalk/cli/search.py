"""CLI: search <query> [--where DSL] [--limit N] [--json] → POST /v4/search.

v4 card search: collide on issue, return each card's current answer; the
optional ``--where`` DSL filters over that current answer.
"""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error
from memorytalk.cli.card import _fmt_search as fmt_search
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import (
    emit_json, emit_json_err, emit_md_err, emit_md_paged,
)
from memorytalk.config import Config


@click.command("search")
@click.argument("query", required=False, default="")
@click.option("--where", "-w", "where", type=str, default=None,
              help="DSL filter over each card's current answer")
@click.option("--limit", "limit", type=int, default=20, show_default=True,
              help="Max cards to return")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def search(query: str, where: str | None, limit: int, json_out: bool) -> None:
    """Find cards by issue/claim relevance (+ optional where DSL)."""
    cfg = Config()
    body: dict = {"query": query or "", "limit": limit}
    if where:
        body["where"] = where
    try:
        result = api("POST", "/v4/search", cfg, json_body=body)
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
        emit_md_paged(fmt_search(result))
