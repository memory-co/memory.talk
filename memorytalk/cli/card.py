"""CLI: card '<json>' [--json].

Accepts the full Card payload as a single JSON string (one positional
argument) to keep the surface tight — the schema isn't simple enough
for individual flags, and writing JSON is what the LLM tool-use path
will do anyway.
"""
from __future__ import annotations
import json
import sys

import click

from memorytalk.cli._format import fmt_card_created, fmt_error
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("card")
@click.argument("payload", type=str)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def card(payload: str, json_out: bool) -> None:
    """Create a Talk-Card from a JSON payload."""
    cfg = Config()
    try:
        body = json.loads(payload)
    except json.JSONDecodeError as e:
        msg = f"invalid JSON payload: {e}"
        if json_out:
            emit_json_err(msg)
        else:
            emit_md_err(fmt_error(msg))
        sys.exit(1)

    try:
        result = api("POST", "/v3/cards", cfg, json_body=body)
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
        emit_md(fmt_card_created(result))
