"""CLI: review '<json>' [--json]."""
from __future__ import annotations
import json
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_review_created
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("review")
@click.argument("payload", type=str)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def review(payload: str, json_out: bool) -> None:
    """Attach a stance (+1 / 0 / -1) review to a card."""
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
        result = api("POST", "/v3/reviews", cfg, json_body=body)
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
        emit_md(fmt_review_created(result))
