"""CLI: read <id> [--json] → POST /v3/read."""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_read
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import (
    emit_json, emit_json_err, emit_md_err, emit_md_paged,
)
from memorytalk.config import Config


@click.command("read")
@click.argument("object_id")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def read(object_id: str, json_out: bool) -> None:
    """Read a card or session by prefixed id."""
    cfg = Config()
    try:
        result = api("POST", "/v3/read", cfg, json_body={"id": object_id})
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
        # Card / session payloads can be long (rounds + reviews +
        # source_cards); route through a less-style pager when in an
        # interactive terminal. Subprocess / pipe / --no-pager fall
        # back to plain output — see emit_md_paged docstring.
        emit_md_paged(fmt_read(result))
