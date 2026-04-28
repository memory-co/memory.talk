"""CLI: link create <json> [--json] → POST /v2/links."""
from __future__ import annotations
import json
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_link_create
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.group("link")
def link() -> None:
    """Manage user links."""


@link.command("create")
@click.argument("body_json")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def link_create(body_json: str, data_root: str | None, json_out: bool) -> None:
    cfg = Config(data_root) if data_root else Config()
    try:
        body = json.loads(body_json)
    except json.JSONDecodeError as e:
        if json_out:
            emit_json_err(f"invalid json: {e}")
        else:
            emit_md_err(fmt_error(f"invalid json: {e}"))
        sys.exit(1)
    try:
        result = api("POST", "/v2/links", cfg, json_body=body)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_link_create(result))
