"""raw command — read original conversation rounds."""

import json

import click

from memory_talk.config import Config
from memory_talk.storage.session_store import SessionStore
from memory_talk.storage.sqlite_store import SQLiteRelationStore


@click.group()
def raw():
    """Access raw conversation data."""
    pass


@raw.command()
@click.argument("session_id")
@click.argument("start", required=False, default=None, type=int)
@click.argument("end", required=False, default=None, type=int)
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def read(session_id: str, start: int | None, end: int | None, data_root: str | None):
    """Read original rounds from a session."""
    config = Config.load(data_root)

    # Find source
    relation = SQLiteRelationStore(config.relation_db_path)
    all_sessions = relation.list_sessions()
    source = None
    for s in all_sessions:
        if s["session_id"] == session_id:
            source = s["source"]
            break

    if source is None:
        click.echo(json.dumps({"error": f"Session not found: {session_id}"}), err=True)
        raise SystemExit(1)

    session_store = SessionStore(config.sessions_dir)
    if start is not None and end is not None:
        rounds = session_store.read_range(source, session_id, start, end)
    else:
        rounds = session_store.read(source, session_id)

    click.echo(json.dumps([r.model_dump(mode="json") for r in rounds], indent=2, default=str))
