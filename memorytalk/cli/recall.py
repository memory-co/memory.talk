"""CLI: recall <session_id> <prompt> [--top-k N] [--json] → POST /v2/recall."""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_recall
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("recall")
@click.argument("session_id")
@click.argument("prompt")
@click.option("--top-k", type=int, default=None, help="Top-k (default from settings.recall)")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def recall(session_id: str, prompt: str, top_k: int | None,
           data_root: str | None, json_out: bool) -> None:
    """Hook-stage memory recall: top-K cards inlined for the AI context."""
    cfg = Config(data_root) if data_root else Config()
    body = {"session_id": session_id, "query": prompt}
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v2/recall", cfg, json_body=body, timeout=30.0)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_recall(result))
