"""CLI: tag add|remove <session_id> <tags...>."""
from __future__ import annotations
import json
import sys

import click

from memory_talk_v2.cli._http import ApiError, api
from memory_talk_v2.config import Config


@click.group("tag")
def tag() -> None:
    """Add / remove tags on a session."""


@tag.command("add")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
@click.option("--data-root", type=click.Path(), default=None)
def tag_add(session_id: str, tags: tuple[str, ...], data_root: str | None) -> None:
    _call("/v2/tags/add", session_id, list(tags), data_root)


@tag.command("remove")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
@click.option("--data-root", type=click.Path(), default=None)
def tag_remove(session_id: str, tags: tuple[str, ...], data_root: str | None) -> None:
    _call("/v2/tags/remove", session_id, list(tags), data_root)


def _call(path: str, session_id: str, tags: list[str], data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    try:
        result = api("POST", path, cfg, json_body={"session_id": session_id, "tags": tags})
        click.echo(json.dumps(result, ensure_ascii=False))
    except ApiError as e:
        click.echo(json.dumps({"error": e.payload}, ensure_ascii=False))
        sys.exit(1)
