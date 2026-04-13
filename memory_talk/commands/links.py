"""links command — create links between existing cards."""

import json

import click

from memory_talk.config import Config
from memory_talk.models import CardLink
from memory_talk.storage.sqlite_store import SQLiteRelationStore


@click.group()
def links():
    """Manage Card Links."""
    pass


@links.command()
@click.argument("link_json")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def create(link_json: str, data_root: str | None):
    """Create a link between two existing cards."""
    config = Config.load(data_root)

    try:
        data = json.loads(link_json)
    except json.JSONDecodeError as e:
        click.echo(json.dumps({"error": f"Invalid JSON: {e}"}), err=True)
        raise SystemExit(1)

    link = CardLink(**data)
    relation = SQLiteRelationStore(config.relation_db_path)
    relation.save_link(link)

    click.echo(json.dumps({"status": "ok", "link": link.model_dump()}, indent=2))
