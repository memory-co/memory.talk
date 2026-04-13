"""setup command — first-time environment configuration."""

import json
from pathlib import Path

import click

from memory_talk.config import Config


@click.command()
@click.option("--vector", default="lancedb", type=click.Choice(["lancedb"]), help="Vector store backend")
@click.option("--relation", default="sqlite", type=click.Choice(["sqlite"]), help="Relation store backend")
@click.option("--embedding", default="local", type=click.Choice(["local", "dummy"]), help="Embedding backend")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def setup(vector: str, relation: str, embedding: str, data_root: str | None):
    """Initialize storage backends and directory structure."""
    root = Path(data_root) if data_root else None
    config = Config.load(root)
    config.vector_backend = vector
    config.relation_backend = relation
    config.embedding_backend = embedding

    # Create directory structure
    config.sessions_dir.mkdir(parents=True, exist_ok=True)
    config.cards_dir.mkdir(parents=True, exist_ok=True)
    config.vectors_dir.mkdir(parents=True, exist_ok=True)
    config.relation_db_path.parent.mkdir(parents=True, exist_ok=True)

    config.save()

    result = {
        "status": "ok",
        "data_root": str(config.data_root),
        "vector_backend": config.vector_backend,
        "relation_backend": config.relation_backend,
        "embedding_backend": config.embedding_backend,
    }
    click.echo(json.dumps(result, indent=2))
