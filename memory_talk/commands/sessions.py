"""sessions command — list, read, mark-built."""

import json

import click

from memory_talk.config import Config
from memory_talk.storage.session_store import SessionStore
from memory_talk.storage.sqlite_store import SQLiteRelationStore


@click.group()
def sessions():
    """Manage imported sessions."""
    pass


@sessions.command("list")
@click.option("--unbuilt", is_flag=True, help="Show only unbuilt sessions")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def list_sessions(unbuilt: bool, data_root: str | None):
    """List sessions."""
    config = Config.load(data_root)
    relation = SQLiteRelationStore(config.relation_db_path)
    result = relation.list_sessions(unbuilt_only=unbuilt)
    click.echo(json.dumps(result, indent=2, default=str))


@sessions.command()
@click.argument("session_id")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def read(session_id: str, data_root: str | None):
    """Read session rounds."""
    config = Config.load(data_root)

    # Find source from relation store
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
    rounds = session_store.read(source, session_id)
    click.echo(json.dumps([r.model_dump(mode="json") for r in rounds], indent=2, default=str))


@sessions.command("mark-built")
@click.argument("session_id")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def mark_built(session_id: str, data_root: str | None):
    """Mark a session as built."""
    config = Config.load(data_root)
    relation = SQLiteRelationStore(config.relation_db_path)
    relation.mark_session_built(session_id)
    click.echo(json.dumps({"status": "ok", "session_id": session_id}))
