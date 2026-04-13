"""recall command — vector search for relevant cards."""

import json

import click

from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.storage.card_store import CardStore
from memory_talk.storage.lancedb_store import LanceDBVectorStore
from memory_talk.storage.sqlite_store import SQLiteRelationStore


@click.command()
@click.argument("query")
@click.option("--top-k", default=5, help="Number of results")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def recall(query: str, top_k: int, data_root: str | None):
    """Vector search for relevant Talk-Cards."""
    config = Config.load(data_root)

    embedder = get_embedder(config.embedding_backend, config.embedding_model)
    query_embedding = embedder.embed_one(query)

    vector_store = LanceDBVectorStore(config.vectors_dir)
    results = vector_store.search(query_embedding, top_k=top_k)

    # Enrich with full card data
    card_store = CardStore(config.cards_dir)
    enriched = []
    for r in results:
        card = card_store.read(r["card_id"])
        if card:
            enriched.append({
                "card_id": card.card_id,
                "cognition_summary": card.cognition_summary,
                "compressed_rounds": card.compressed_rounds,
                "raw_ref": card.raw_ref.model_dump(),
                "distance": r.get("distance", 0.0),
            })

    click.echo(json.dumps({"query": query, "results": enriched, "count": len(enriched)}, indent=2))
