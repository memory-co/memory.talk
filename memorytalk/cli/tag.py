"""CLI: tag add|remove <subject_id> ... [--json].

Subject id may be ``sess_*`` or ``card_*``; the CLI picks the right
URL prefix automatically. Card support is wired through TagService at
this point — the subject-id prefix dispatch happens server-side.

`tag remove` takes **keys** only (no ``key:value``); the CLI rejects
inputs containing ``:`` to make the contract obvious.
"""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_tag
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config
from memorytalk.util.ids import CARD_PREFIX, SESSION_PREFIX


def _route_for(subject_id: str) -> str:
    if subject_id.startswith(SESSION_PREFIX):
        return f"/v2/sessions/{subject_id}/tags"
    if subject_id.startswith(CARD_PREFIX):
        return f"/v2/cards/{subject_id}/tags"
    raise click.BadParameter(
        "subject_id must start with sess_ or card_",
        param_hint="<subject_id>",
    )


@click.group("tag")
def tag() -> None:
    """Add / remove tags on a session or card."""


@tag.command("add")
@click.argument("subject_id")
@click.argument("tags", nargs=-1, required=True)
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def tag_add(subject_id: str, tags: tuple[str, ...], data_root: str | None, json_out: bool) -> None:
    path = _route_for(subject_id)
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("POST", path, cfg, json_body={"tags": list(tags)})
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_tag(result))


@tag.command("remove")
@click.argument("subject_id")
@click.argument("keys", nargs=-1, required=True)
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def tag_remove(subject_id: str, keys: tuple[str, ...], data_root: str | None, json_out: bool) -> None:
    bad = [k for k in keys if ":" in k]
    if bad:
        raise click.BadParameter(
            f"tag remove takes keys only, not key:value (got: {', '.join(bad)})",
            param_hint="<keys>",
        )
    path = _route_for(subject_id)
    cfg = Config(data_root) if data_root else Config()
    params = [("key", k) for k in keys]
    try:
        result = api("DELETE", path, cfg, params=params)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_tag(result))
