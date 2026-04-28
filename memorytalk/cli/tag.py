"""CLI: tag add|remove <session_id> <tags...> [--json]."""
from __future__ import annotations
import sys

import click

from memory_talk_v2.cli._format import fmt_error, fmt_tag
from memory_talk_v2.cli._http import ApiError, api, extract_error_message
from memory_talk_v2.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memory_talk_v2.config import Config


@click.group("tag")
def tag() -> None:
    """Add / remove tags on a session."""


@tag.command("add")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def tag_add(session_id: str, tags: tuple[str, ...], data_root: str | None, json_out: bool) -> None:
    _call("/v2/tags/add", session_id, list(tags), data_root, json_out)


@tag.command("remove")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
def tag_remove(session_id: str, tags: tuple[str, ...], data_root: str | None, json_out: bool) -> None:
    _call("/v2/tags/remove", session_id, list(tags), data_root, json_out)


def _call(path: str, session_id: str, tags: list[str],
          data_root: str | None, json_out: bool) -> None:
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("POST", path, cfg, json_body={"session_id": session_id, "tags": tags})
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
