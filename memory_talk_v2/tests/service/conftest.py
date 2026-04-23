"""Service-layer test fixtures — real SQLite + LanceDB + dummy embedder."""
from __future__ import annotations
from pathlib import Path

import pytest

from memory_talk_v2.config import Config
from memory_talk_v2.embedding import DummyEmbedder
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.storage import files as F
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
    search_jsonl = DatedJsonlWriter(cfg.search_log_dir)
    events = EventWriter(cfg, db)

    def _events_for(object_id: str) -> list[dict]:
        """Helper: read events.jsonl for a card or session via file layer."""
        if object_id.startswith("card_"):
            return F.read_card_events(cfg.cards_dir, object_id)
        if object_id.startswith("sess_"):
            s = db.get_session(object_id)
            if s is None:
                return []
            return F.read_session_events(cfg.sessions_dir, s["source"], object_id)
        raise ValueError(f"unknown object prefix: {object_id}")

    class Bundle:
        pass

    b = Bundle()
    b.config = cfg
    b.db = db
    b.vectors = vectors
    b.embedder = embedder
    b.events = events
    b.search_jsonl = search_jsonl
    b.events_for = _events_for
    yield b
    db.close()
