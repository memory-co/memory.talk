"""CLI: view <id> [--json] → POST /v2/view."""
from __future__ import annotations
import sys

import click

from memory_talk_v2.cli._format import fmt_error, fmt_view
from memory_talk_v2.cli._http import ApiError, api, extract_error_message
from memory_talk_v2.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memory_talk_v2.config import Config


@click.command("view")
@click.argument("object_id")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def view(object_id: str, data_root: str | None, json_out: bool) -> None:
    """Read a card or session by prefixed id."""
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("POST", "/v2/view", cfg, json_body={"id": object_id})
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_view(result))
