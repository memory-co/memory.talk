"""CLI: memory.talk card {create, list, tag} — card write + maintenance.

Three subcommands:

  create  write a new immutable card (was the bare ``card '<json>'`` form
          in 0.7.x; hard-renamed in 0.8.x because the top level now hosts
          list / tag too)
  list    multi-filter listing (tag / created_at) — no source/cwd: cards
          aren't from a source the way sessions are
  tag     query / set / unset kv tags on one card

The HTTP-call shape is identical to ``cli/session.py`` — both go through
the same ``api()`` helper and share fmt_/parse_ helpers. See
``docs/cli/v3/card.md`` for the user-facing contract.
"""
from __future__ import annotations
import json
import sys

import click

from memorytalk.cli._format import (
    fmt_card_created, fmt_card_list, fmt_card_tag, fmt_error,
)
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
# Shared with cli/session.py — same duration grammar, same error pathway.
# Imported (not duplicated) so a future grammar change lands in one place.
from memorytalk.cli.session import _duration_to_iso, _emit_err
from memorytalk.config import Config
from memorytalk.util.tags import TagValidationError, parse_kv_args


@click.group("card")
def card() -> None:
    """Card write + maintenance: create / list / tag."""


# ────────── card create ──────────

@card.command("create")
@click.argument("payload", type=str)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def create(payload: str, json_out: bool) -> None:
    """Create a Talk-Card from a JSON payload."""
    cfg = Config()
    try:
        body = json.loads(payload)
    except json.JSONDecodeError as e:
        _emit_err(json_out, f"invalid JSON payload: {e}")
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
        _emit_err(json_out, f"cannot reach server: {e}")
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_card_created(result))


# ────────── card list ──────────

@card.command("list")
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
def list_(
    tags: tuple[str, ...], since: str | None, until: str | None,
    limit: int, json_out: bool,
) -> None:
    """List cards by structural filters (tag + time)."""
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
        result = api("GET", "/v3/cards", cfg, params=params)
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
        emit_md(fmt_card_list(result, filter_summary))


# ────────── card tag ──────────

@card.command("tag")
@click.argument("card_id")
@click.argument("kv_args", nargs=-1)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def tag(card_id: str, kv_args: tuple[str, ...], json_out: bool) -> None:
    """Query / set / unset kv tags on a card.

    No positional args after <card_id> → query current tags.
    """
    cfg = Config()

    try:
        set_, unset = parse_kv_args(kv_args)
    except TagValidationError as e:
        _emit_err(json_out, str(e))
        sys.exit(1)

    body = {"set": set_, "unset": unset}
    try:
        result = api(
            "PATCH", f"/v3/cards/{card_id}/tags",
            cfg, json_body=body,
        )
    except ApiError as e:
        _emit_err(json_out, extract_error_message(e.payload))
        sys.exit(1)
    except Exception as e:
        _emit_err(json_out, f"cannot reach server: {e}")
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        is_query = not (set_ or unset)
        emit_md(fmt_card_tag(result, is_query=is_query))


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
