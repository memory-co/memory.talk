"""Service-layer test fixtures — real SQLite + LanceDB + dummy embedder."""
from __future__ import annotations
from pathlib import Path

import pytest

from memory_talk_v2.config import Config
from memory_talk_v2.embedding import DummyEmbedder
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.storage.jsonl_writer import DatedJsonlWriter
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


@pytest.fixture
def services(tmp_path: Path):
    data_root = tmp_path / ".mt"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        '{"embedding": {"provider": "dummy", "dim": 384},'
        ' "ttl": {"card": {"initial": 3600, "factor": 2.0, "max": 86400},'
        '         "link": {"initial": 1800, "factor": 2.0, "max": 43200}}}'
    )
    cfg = Config(data_root)
    cfg.ensure_dirs()
    db = SQLiteStore(cfg.db_path)
    vectors = LanceStore(cfg.vectors_dir, dim=cfg.settings.embedding.dim)
    embedder = DummyEmbedder(dim=cfg.settings.embedding.dim)
    event_jsonl = DatedJsonlWriter(cfg.event_log_dir)
    search_jsonl = DatedJsonlWriter(cfg.search_log_dir)
    events = EventWriter(event_jsonl, db)

    class Bundle:
        pass

    b = Bundle()
    b.config = cfg
    b.db = db
    b.vectors = vectors
    b.embedder = embedder
    b.events = events
    b.event_jsonl = event_jsonl
    b.search_jsonl = search_jsonl
    yield b
    db.close()
