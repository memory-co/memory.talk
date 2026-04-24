"""Shared dependency bundle for all service classes."""
from __future__ import annotations
from dataclasses import dataclass

from memory_talk_v2.config import Config
from memory_talk_v2.embedding import Embedder
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.storage.jsonl_writer import DatedJsonlWriter
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


@dataclass
class ServiceContext:
    config: Config
    db: SQLiteStore
    vectors: LanceStore
    embedder: Embedder
    search_jsonl: DatedJsonlWriter
    events: EventWriter
