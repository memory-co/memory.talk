"""CLI: memory.talk insight {search, view} — read-only old card.

Insight is the renamed v3 card, kept READ-ONLY in v4 (the ``card`` name is
now owned by the v4 question-graph). Ids carry the ``insight_`` prefix.

Subcommands:

  search  list / filter insights (tag + created_at) via GET /v4/insights
  view    show one insight by id via POST /v4/read (prefix-dispatched)

See ``docs/cli/v4/insight.md`` for the user-facing contract.
"""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_insight_list, fmt_error
from memorytalk.cli.card import _fmt_read as fmt_read
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import (
    emit_json, emit_json_err, emit_md, emit_md_err, emit_md_paged,
)
# Shared with cli/session.py — same duration grammar, same error pathway.
from memorytalk.cli.session import _duration_to_iso, _emit_err
from memorytalk.config import Config


@click.group("insight")
def insight() -> None:
    """Read-only old card: search / view."""


# ────────── insight search ──────────

@insight.command("search")
@click.option("--tag", "tags", multiple=True,
              help="K=V (eq), K!=V (ne, NULL excluded), K=V1,V2 (in), "
                   "K (present), !K (absent); repeatable, AND")
@click.option("--since", "-d", "since", type=str, default=None,
              help="Lower bound on created_at: '7d' / '12h' / '2w' / ISO")
@click.option("--until", type=str, default=None,
              help="Upper bound on created_at: same syntax as --since")
@click.option("--limit", type=int, default=20, show_default=True,
              help="Max rows to return (1..200)")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def search(
    tags: tuple[str, ...], since: str | None, until: str | None,
    limit: int, json_out: bool,
) -> None:
    """List insights by structural filters (tag + time)."""
    cfg = Config()

    try:
        since_iso = _duration_to_iso(since)
        until_iso = _duration_to_iso(until)
    except click.BadParameter as e:
        _emit_err(json_out, str(e))
        sys.exit(1)

    params: list[tuple[str, str]] = []
    for t in tags:
        params.append(("tag", t))
    if since_iso:
        params.append(("since", since_iso))
    if until_iso:
        params.append(("until", until_iso))
    params.append(("limit", str(limit)))

    try:
        result = api("GET", "/v4/insights", cfg, params=params)
    except ApiError as e:
        _emit_err(json_out, extract_error_message(e.payload))
        sys.exit(1)
    except Exception as e:
        _emit_err(json_out, f"cannot reach server: {e}")
        sys.exit(1)

    filter_summary = _summarize_filters(tags, since, until)
    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_insight_list(result, filter_summary))


# ────────── insight view ──────────

@insight.command("view")
@click.argument("insight_id")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def view(insight_id: str, json_out: bool) -> None:
    """Show one insight by id (read-only)."""
    cfg = Config()
    try:
        result = api("POST", "/v4/read", cfg, json_body={"id": insight_id})
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)
    except Exception as e:
        _emit_err(json_out, f"cannot reach server: {e}")
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md_paged(fmt_read(result))


# ────────── helpers ──────────

def _summarize_filters(
    tags: tuple[str, ...], since: str | None, until: str | None,
) -> str:
    parts: list[str] = []
    for t in tags:
        parts.append(f"tag={t}")
    if since:
        parts.append(f"since={since}")
    if until:
        parts.append(f"until={until}")
    return " · ".join(parts)
