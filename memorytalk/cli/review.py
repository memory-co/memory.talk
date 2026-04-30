"""CLI: review list / detail — read-only navigation over recall history."""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import (
    fmt_error, fmt_review_detail, fmt_review_list,
)
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.group("review")
def review() -> None:
    """Navigate recall history."""


@review.command("list")
@click.option("--limit", type=int, default=100, show_default=True)
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def review_list(limit: int, data_root: str | None, json_out: bool) -> None:
    """List sessions with recall history (most recent first)."""
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("GET", f"/v2/review/list?limit={limit}", cfg, timeout=10.0)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_review_list(result))


@review.command("detail")
@click.argument("session_id")
@click.option("--limit", type=int, default=50, show_default=True,
              help="Most recent N rounds")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def review_detail(session_id: str, limit: int, data_root: str | None, json_out: bool) -> None:
    """Drill into one session — per-round hit history."""
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("GET", f"/v2/review/detail/{session_id}?limit={limit}", cfg, timeout=10.0)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_review_detail(result))
