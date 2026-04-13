"""status command — show storage statistics."""

import json

import click

from memory_talk.config import Config
from memory_talk.storage.sqlite_store import SQLiteRelationStore


@click.command()
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def status(data_root: str | None):
    """Show storage statistics."""
    config = Config.load(data_root)

    if not config.relation_db_path.exists():
        click.echo(json.dumps({"error": "Not initialized. Run 'memory-talk setup' first."}), err=True)
        raise SystemExit(1)

    relation = SQLiteRelationStore(config.relation_db_path)
    all_sessions = relation.list_sessions()
    unbuilt = relation.list_sessions(unbuilt_only=True)
    all_cards = relation.list_cards()

    result = {
        "data_root": str(config.data_root),
        "sessions_total": len(all_sessions),
        "sessions_unbuilt": len(unbuilt),
        "cards_total": len(all_cards),
        "vector_backend": config.vector_backend,
        "relation_backend": config.relation_backend,
        "embedding_backend": config.embedding_backend,
    }
    click.echo(json.dumps(result, indent=2))
