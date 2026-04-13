"""cards command — create, get, list, links."""

import json
import sys

import click

from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.models import CardLink, RawRef, TalkCard
from memory_talk.storage.card_store import CardStore
from memory_talk.storage.lancedb_store import LanceDBVectorStore
from memory_talk.storage.sqlite_store import SQLiteRelationStore


@click.group()
def cards():
    """Manage Talk-Cards."""
    pass


@cards.command()
@click.argument("card_json")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def create(card_json: str, data_root: str | None):
    """Create a Talk-Card from JSON. Auto-computes embedding."""
    config = Config.load(data_root)

    try:
        data = json.loads(card_json)
    except json.JSONDecodeError as e:
        click.echo(json.dumps({"error": f"Invalid JSON: {e}"}), err=True)
        raise SystemExit(1)

    # Generate card_id if not provided
    if "card_id" not in data:
        from ulid import ULID
        data["card_id"] = str(ULID()).lower()

    # Build RawRef
    if "raw_ref" not in data and "session_id" in data:
        data["raw_ref"] = {
            "session_id": data.pop("session_id"),
            "round_start": data.pop("round_start", 0),
            "round_end": data.pop("round_end", 0),
        }

    # Build links
    card_links = []
    if "links" in data:
        for lk in data.pop("links"):
            lk.setdefault("source_card_id", data["card_id"])
            card_links.append(CardLink(**lk))
    data["links"] = card_links

    card = TalkCard(**data)

    # Save to file store
    card_store = CardStore(config.cards_dir)
    card_store.save(card)

    # Save to relation store
    relation = SQLiteRelationStore(config.relation_db_path)
    relation.save_card(card)

    # Compute embedding and save to vector store
    embedder = get_embedder(config.embedding_backend, config.embedding_model)
    text = f"{card.cognition_summary}\n{card.compressed_rounds}"
    embedding = embedder.embed_one(text)

    vector_store = LanceDBVectorStore(config.vectors_dir)
    vector_store.add_card(
        card_id=card.card_id,
        text=text,
        embedding=embedding,
        metadata={"session_id": card.raw_ref.session_id},
    )

    click.echo(json.dumps({"status": "ok", "card_id": card.card_id}, indent=2))


@cards.command()
@click.argument("card_id")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def get(card_id: str, data_root: str | None):
    """Read a Talk-Card."""
    config = Config.load(data_root)
    card_store = CardStore(config.cards_dir)
    card = card_store.read(card_id)
    if card is None:
        click.echo(json.dumps({"error": f"Card not found: {card_id}"}), err=True)
        raise SystemExit(1)
    click.echo(card.model_dump_json(indent=2))


@cards.command("list")
@click.option("--session-id", default=None, help="Filter by session ID")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def list_cards(session_id: str | None, data_root: str | None):
    """List Talk-Cards."""
    config = Config.load(data_root)
    relation = SQLiteRelationStore(config.relation_db_path)
    result = relation.list_cards(session_id=session_id)
    click.echo(json.dumps(result, indent=2, default=str))


@cards.command()
@click.argument("card_id")
@click.option("--data-root", default=None, type=click.Path(), help="Data root directory")
def links(card_id: str, data_root: str | None):
    """Get cards linked to this card."""
    config = Config.load(data_root)
    relation = SQLiteRelationStore(config.relation_db_path)

    link_rows = relation.get_links(card_id)
    linked_card_ids = set()
    for lk in link_rows:
        linked_card_ids.add(lk["source_card_id"])
        linked_card_ids.add(lk["target_card_id"])
    linked_card_ids.discard(card_id)

    card_store = CardStore(config.cards_dir)
    linked_cards = []
    for cid in linked_card_ids:
        card = card_store.read(cid)
        if card:
            linked_cards.append(card.model_dump(mode="json"))

    click.echo(json.dumps({"card_id": card_id, "links": link_rows, "linked_cards": linked_cards}, indent=2, default=str))
