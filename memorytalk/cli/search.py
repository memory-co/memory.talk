"""CLI: search <query> [--where DSL] [--top-k N] [--json]."""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_search
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import (
    emit_json, emit_json_err, emit_md_err, emit_md_paged,
)
from memorytalk.config import Config


@click.command("search")
@click.argument("query", required=False, default="")
@click.option("--where", "-w", "where", type=str, default=None,
              help="DSL filter (see docs/cli/v3/search.md#DSL)")
@click.option("--top-k", "top_k", type=int, default=None,
              help="Total result cap (default = settings.search.default_top_k)")
@click.option("--recall", "recall_mode", is_flag=True, default=False,
              help="Debug lens: rank like `recall` (cards-only, raw RRF, "
                   "no ranking_formula). Combine with --session to also "
                   "preview that session's recall_log dedup. Read-only — "
                   "does NOT bump recall_count or write recall_log.")
@click.option("--session", "session_id", type=str, default=None,
              help="Session id for recall-mode dedup (only meaningful "
                   "with --recall).")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def search(
    query: str, where: str | None, top_k: int | None,
    recall_mode: bool, session_id: str | None, json_out: bool,
) -> None:
    """Hybrid FTS + vector search across cards and sessions."""
    cfg = Config()
    body: dict = {"query": query or ""}
    if where:
        body["where"] = where
    if top_k is not None:
        body["top_k"] = top_k
    if recall_mode:
        body["recall_mode"] = True
    if session_id:
        if not recall_mode:
            # --session without --recall is a probable mistake; flag it
            # rather than silently dropping the field.
            emit_md_err(fmt_error(
                "--session only takes effect with --recall (it scopes "
                "the recall-log dedup preview)"
            ))
            sys.exit(1)
        body["recall_session_id"] = session_id
    try:
        result = api("POST", "/v3/search", cfg, json_body=body)
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
        # Long result blocks (cards + per-session hit fences + ctx
        # windows) routinely exceed a terminal page; route through the
        # same less-style pager that ``read`` uses. Subprocess / pipe /
        # ``--no-pager`` / ``--json`` fall back to plain output — see
        # emit_md_paged docstring.
        emit_md_paged(fmt_search(result))
