"""explore command — discover and import conversations."""

import hashlib
import json

import click

from memory_talk.adapters.registry import get_adapter
from memory_talk.config import Config
from memory_talk.storage.session_store import SessionStore
from memory_talk.storage.sqlite_store import SQLiteRelationStore


@click.group()
def explore():
    """Discover and import conversations from platforms."""
    pass


@explore.command()
@click.option("--source", required=True, help="Platform adapter name (e.g. claude-code)")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def scan(source: str, data_root: str | None):
    """List sessions not yet imported."""
    config = Config.load(data_root)
    adapter = get_adapter(source)
    relation = SQLiteRelationStore(config.relation_db_path)

    all_paths = adapter.discover()
    new_paths = []
    for path in all_paths:
        file_hash = _file_hash(path)
        if not relation.is_ingested(str(path), file_hash):
            new_paths.append({"path": str(path), "hash": file_hash})

    click.echo(json.dumps({"source": source, "new_sessions": new_paths, "total": len(new_paths)}, indent=2))


@explore.command()
@click.argument("session_path")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def ingest(session_path: str, data_root: str | None):
    """Import a single session file."""
    from pathlib import Path

    config = Config.load(data_root)
    source_path = Path(session_path)

    if not source_path.exists():
        click.echo(json.dumps({"error": f"File not found: {session_path}"}), err=True)
        raise SystemExit(1)

    # Detect adapter from path (sessions are under platform project dirs)
    # For now, assume claude-code if under ~/.claude/
    adapter = get_adapter("claude-code")
    session = adapter.convert(source_path)

    # Save raw JSONL
    session_store = SessionStore(config.sessions_dir)
    session_store.save(session)

    # Save metadata to relation store
    relation = SQLiteRelationStore(config.relation_db_path)
    relation.save_session(
        session_id=session.session_id,
        source=session.source,
        metadata=session.metadata,
        round_count=len(session.rounds),
    )

    # Log ingest
    file_hash = _file_hash(source_path)
    relation.log_ingest(str(source_path), session.session_id, file_hash)

    click.echo(json.dumps({
        "status": "ok",
        "session_id": session.session_id,
        "source": session.source,
        "rounds": len(session.rounds),
    }, indent=2))


def _file_hash(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]
