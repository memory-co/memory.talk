"""CLI: rebuild [--json] → POST /v2/rebuild."""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_rebuild
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("rebuild")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def rebuild(data_root: str | None, json_out: bool) -> None:
    """Blocking rebuild of SQLite + LanceDB from file-layer truth."""
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("POST", "/v2/rebuild", cfg, timeout=600.0)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_rebuild(result))
