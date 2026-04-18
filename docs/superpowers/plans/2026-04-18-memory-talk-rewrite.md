# memory.talk 完整重写实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 docs/ 规格，从零重写 memory_talk/ Python 工程，4 层架构（CLI → API → Service → Storage），场景测试对应 stories/s1/。

**Architecture:** FastAPI 本地 server + Click CLI 管控。CLI 通过 HTTP 调 API，sync 是唯一直接读平台文件的胶水命令。TTL 用 expires_at 时间戳 + factor 刷新实现遗忘曲线。

**Tech Stack:** Python 3.10+, FastAPI, Click, Pydantic 2, SQLite, LanceDB, httpx, python-ulid

**Spec:** `docs/superpowers/specs/2026-04-18-memory-talk-rewrite-design.md`

---

### Task 1: 清理旧代码 + 项目配置

**Files:**
- Delete: `memory_talk/` (全部), `tests/` (全部)
- Create: `memory_talk/__init__.py`, `memory_talk/__main__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 删除旧代码**

```bash
rm -rf memory_talk/ tests/
mkdir -p memory_talk tests
```

- [ ] **Step 2: 创建包入口**

```python
# memory_talk/__init__.py
"""memory.talk — persistent cross-session memory for AI agents."""

# memory_talk/__main__.py
from memory_talk.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 更新 pyproject.toml**

```toml
[project]
name = "memory-talk"
version = "0.3.0"
description = "Persistent cross-session memory for AI agents via Talk-Card architecture"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0.0",
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "httpx>=0.25.0",
    "lancedb>=0.6.0",
    "numpy>=1.24.0",
    "python-ulid>=2.0.0",
]

[project.scripts]
memory-talk = "memory_talk.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
]
local = [
    "sentence-transformers>=2.2.0",
]

[tool.setuptools.packages.find]
include = ["memory_talk*"]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: clean slate for rewrite, update pyproject.toml"
```

---

### Task 2: 数据模型 (models/)

**Files:**
- Create: `memory_talk/models/__init__.py`
- Create: `memory_talk/models/session.py`
- Create: `memory_talk/models/card.py`
- Create: `memory_talk/models/link.py`

- [ ] **Step 1: Session 模型**

```python
# memory_talk/models/session.py
"""Session data model — raw conversation from platforms."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str

class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    language: str
    text: str

class ThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str

ContentBlock = Union[TextBlock, CodeBlock, ThinkingBlock]


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class Round(BaseModel):
    round_id: str
    parent_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    speaker: str
    role: str  # human / assistant / system / tool
    content: list[ContentBlock]
    is_sidechain: bool = False
    cwd: Optional[str] = None
    usage: Optional[Usage] = None


class Session(BaseModel):
    session_id: str
    source: str
    created_at: Optional[datetime] = None
    metadata: dict[str, Any] = {}
    tags: list[str] = []
    rounds: list[Round] = []
    round_count: int = 0
    synced_at: Optional[datetime] = None
```

- [ ] **Step 2: TalkCard 模型**

```python
# memory_talk/models/card.py
"""Talk-Card data model — the core memory unit."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CardRound(BaseModel):
    role: str  # human / assistant
    text: str
    thinking: Optional[str] = None


class CardLinkInput(BaseModel):
    """Link structure used in cards create (simplified)."""
    id: str
    type: str  # session / card
    comment: Optional[str] = None


class TalkCard(BaseModel):
    card_id: str
    summary: str
    session_id: Optional[str] = None
    rounds: list[CardRound]
    links: list[CardLinkInput] = []
    ttl: int = 0  # computed: expires_at - now (seconds)
    created_at: datetime = datetime.now()
```

- [ ] **Step 3: Link 模型**

```python
# memory_talk/models/link.py
"""Link data model — relationship between any two objects."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class Link(BaseModel):
    link_id: str
    source_id: str
    source_type: str  # card / session
    target_id: str
    target_type: str  # card / session
    comment: Optional[str] = None
    ttl: int = 0  # computed: expires_at - now (seconds)
    created_at: datetime = datetime.now()


class LinkCreate(BaseModel):
    """Request body for POST /links."""
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    comment: Optional[str] = None
```

- [ ] **Step 4: __init__.py 导出**

```python
# memory_talk/models/__init__.py
from .session import Session, Round, ContentBlock, TextBlock, CodeBlock, ThinkingBlock, Usage
from .card import TalkCard, CardRound, CardLinkInput
from .link import Link, LinkCreate
```

- [ ] **Step 5: Commit**

```bash
git add memory_talk/models/ && git commit -m "feat: add data models (Session, TalkCard, Link)"
```

---

### Task 3: 配置 + Embedding (config.py, embedding.py)

**Files:**
- Create: `memory_talk/config.py`
- Create: `memory_talk/embedding.py`

- [ ] **Step 1: Config**

```python
# memory_talk/config.py
"""Configuration — reads/writes ~/.memory-talk/settings.json."""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel


class TTLConfig(BaseModel):
    initial: int = 2592000  # 30 days
    factor: float = 2.0
    max: int = 31536000  # 365 days

class TTLSettings(BaseModel):
    card: TTLConfig = TTLConfig()
    link: TTLConfig = TTLConfig(initial=1209600, max=15768000)  # 14d / 182d

class ProviderConfig(BaseModel):
    provider: str = "lancedb"

class EmbeddingConfig(BaseModel):
    provider: str = "dummy"
    model: str = "all-MiniLM-L6-v2"

class Settings(BaseModel):
    vector: ProviderConfig = ProviderConfig(provider="lancedb")
    relation: ProviderConfig = ProviderConfig(provider="sqlite")
    embedding: EmbeddingConfig = EmbeddingConfig()
    ttl: TTLSettings = TTLSettings()


class Config:
    """Resolves paths and loads settings."""

    def __init__(self, data_root: Path | str | None = None):
        self.data_root = Path(data_root) if data_root else Path.home() / ".memory-talk"
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = self._load()
        return self._settings

    @property
    def settings_path(self) -> Path:
        return self.data_root / "settings.json"

    @property
    def sessions_dir(self) -> Path:
        return self.data_root / "sessions"

    @property
    def cards_dir(self) -> Path:
        return self.data_root / "cards"

    @property
    def vectors_dir(self) -> Path:
        return self.data_root / "data" / "vectors"

    @property
    def db_path(self) -> Path:
        return self.data_root / "data" / "relation.db"

    @property
    def pid_path(self) -> Path:
        return self.data_root / "server.pid"

    def ensure_dirs(self) -> None:
        for d in [self.sessions_dir, self.cards_dir, self.vectors_dir, self.db_path.parent]:
            d.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Settings:
        if self.settings_path.exists():
            data = json.loads(self.settings_path.read_text())
            return Settings(**data)
        return Settings()

    def save(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(self.settings.model_dump(), indent=2)
        )
```

- [ ] **Step 2: Embedding**

```python
# memory_talk/embedding.py
"""Embedding abstraction — pure math, no LLM."""
from __future__ import annotations
from abc import ABC, abstractmethod
import hashlib


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class DummyEmbedder(Embedder):
    """Hash-based embedder for testing. Deterministic, no dependencies."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h]
            vec = (vec * ((self.dim // len(vec)) + 1))[: self.dim]
            results.append(vec)
        return results


class LocalEmbedder(Embedder):
    """sentence-transformers embedder."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()


def get_embedder(config) -> Embedder:
    p = config.settings.embedding.provider
    if p == "dummy":
        return DummyEmbedder()
    elif p == "local":
        return LocalEmbedder(config.settings.embedding.model)
    raise ValueError(f"Unknown embedding provider: {p}")
```

- [ ] **Step 3: Commit**

```bash
git add memory_talk/config.py memory_talk/embedding.py && git commit -m "feat: add config and embedding"
```

---

### Task 4: Storage 层 (storage/)

**Files:**
- Create: `memory_talk/storage/__init__.py`
- Create: `memory_talk/storage/init_db.py`
- Create: `memory_talk/storage/sqlite.py`
- Create: `memory_talk/storage/lancedb.py`
- Create: `memory_talk/storage/files.py`

- [ ] **Step 1: init_db.py**

```python
# memory_talk/storage/init_db.py
"""Create SQLite tables."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    metadata TEXT,
    tags TEXT,
    round_count INTEGER,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    card_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    session_id TEXT,
    expires_at REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS links (
    link_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    comment TEXT,
    expires_at REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_log (
    source_path TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.close()
```

- [ ] **Step 2: sqlite.py**

```python
# memory_talk/storage/sqlite.py
"""SQLite storage for sessions metadata, cards metadata, links, ingest log."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # --- sessions ---

    def save_session(self, session_id: str, source: str, metadata: dict, tags: list[str], round_count: int, synced_at: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO sessions (session_id, source, metadata, tags, round_count, synced_at) VALUES (?,?,?,?,?,?)",
                (session_id, source, json.dumps(metadata), json.dumps(tags), round_count, synced_at),
            )

    def list_sessions(self, tag: str | None = None) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM sessions ORDER BY synced_at DESC").fetchall()
        result = [dict(r) for r in rows]
        if tag:
            result = [r for r in result if tag in json.loads(r.get("tags", "[]"))]
        return result

    def get_session(self, session_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def add_tags(self, session_id: str, tags: list[str]) -> None:
        with self._conn() as c:
            row = c.execute("SELECT tags FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row:
                existing = json.loads(row["tags"] or "[]")
                merged = list(set(existing + tags))
                c.execute("UPDATE sessions SET tags=? WHERE session_id=?", (json.dumps(merged), session_id))

    def remove_tags(self, session_id: str, tags: list[str]) -> None:
        with self._conn() as c:
            row = c.execute("SELECT tags FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row:
                existing = json.loads(row["tags"] or "[]")
                remaining = [t for t in existing if t not in tags]
                c.execute("UPDATE sessions SET tags=? WHERE session_id=?", (json.dumps(remaining), session_id))

    # --- cards ---

    def save_card(self, card_id: str, summary: str, session_id: str | None, expires_at: float, created_at: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO cards (card_id, summary, session_id, expires_at, created_at) VALUES (?,?,?,?,?)",
                (card_id, summary, session_id, expires_at, created_at),
            )

    def get_card(self, card_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
        return dict(row) if row else None

    def list_cards(self, session_id: str | None = None) -> list[dict]:
        with self._conn() as c:
            if session_id:
                rows = c.execute("SELECT * FROM cards WHERE session_id=? AND expires_at>? ORDER BY created_at", (session_id, time.time())).fetchall()
            else:
                rows = c.execute("SELECT * FROM cards WHERE expires_at>? ORDER BY created_at", (time.time(),)).fetchall()
        return [dict(r) for r in rows]

    def refresh_card_ttl(self, card_id: str, new_expires_at: float) -> None:
        with self._conn() as c:
            c.execute("UPDATE cards SET expires_at=? WHERE card_id=?", (new_expires_at, card_id))

    # --- links ---

    def save_link(self, link_id: str, source_id: str, source_type: str, target_id: str, target_type: str, comment: str | None, expires_at: float, created_at: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO links (link_id, source_id, source_type, target_id, target_type, comment, expires_at, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (link_id, source_id, source_type, target_id, target_type, comment, expires_at, created_at),
            )

    def get_links(self, obj_id: str, type_filter: str | None = None) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM links WHERE (source_id=? OR target_id=?) AND expires_at>?",
                (obj_id, obj_id, time.time()),
            ).fetchall()
        result = [dict(r) for r in rows]
        if type_filter:
            result = [r for r in result if r["source_type"] == type_filter or r["target_type"] == type_filter]
        return result

    def refresh_link_ttl(self, link_id: str, new_expires_at: float) -> None:
        with self._conn() as c:
            c.execute("UPDATE links SET expires_at=? WHERE link_id=?", (new_expires_at, link_id))

    def delete_link(self, link_id: str) -> bool:
        with self._conn() as c:
            cursor = c.execute("DELETE FROM links WHERE link_id=?", (link_id,))
        return cursor.rowcount > 0

    # --- ingest log ---

    def log_ingest(self, source_path: str, session_id: str, file_hash: str, ingested_at: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ingest_log (source_path, session_id, file_hash, ingested_at) VALUES (?,?,?,?)",
                (source_path, session_id, file_hash, ingested_at),
            )

    def is_ingested(self, source_path: str, file_hash: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT 1 FROM ingest_log WHERE source_path=? AND file_hash=?", (source_path, file_hash)).fetchone()
        return row is not None

    # --- status ---

    def count_sessions(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    def count_cards(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM cards WHERE expires_at>?", (time.time(),)).fetchone()[0]

    def count_links(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM links WHERE expires_at>?", (time.time(),)).fetchone()[0]
```

- [ ] **Step 3: lancedb.py**

```python
# memory_talk/storage/lancedb.py
"""LanceDB vector storage."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import lancedb
import pyarrow as pa


class LanceStore:
    TABLE = "cards"

    def __init__(self, db_path: Path):
        db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(db_path))

    def _table_exists(self) -> bool:
        try:
            self.db.open_table(self.TABLE)
            return True
        except Exception:
            return False

    def _ensure_table(self, dim: int):
        if self._table_exists():
            return self.db.open_table(self.TABLE)
        schema = pa.schema([
            pa.field("card_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ])
        return self.db.create_table(self.TABLE, schema=schema)

    def add(self, card_id: str, text: str, embedding: list[float]) -> None:
        table = self._ensure_table(len(embedding))
        table.add([{"card_id": card_id, "text": text, "vector": embedding}])

    def search(self, query: list[float], top_k: int = 5) -> list[dict]:
        if not self._table_exists():
            return []
        table = self.db.open_table(self.TABLE)
        results = table.search(query).limit(top_k).to_list()
        return [{"card_id": r["card_id"], "text": r["text"], "distance": r.get("_distance", 0.0)} for r in results]

    def delete(self, card_ids: list[str]) -> None:
        if not self._table_exists():
            return
        table = self.db.open_table(self.TABLE)
        ids = ", ".join(f"'{c}'" for c in card_ids)
        table.delete(f"card_id IN ({ids})")
```

- [ ] **Step 4: files.py**

```python
# memory_talk/storage/files.py
"""File-based storage for sessions (JSONL) and cards (JSON)."""
from __future__ import annotations
import json
from pathlib import Path
from memory_talk.models.session import Session, Round
from memory_talk.models.card import TalkCard


class SessionFiles:
    def __init__(self, base: Path):
        self.base = base

    def _path(self, source: str, session_id: str) -> Path:
        return self.base / source / session_id[:2] / f"{session_id}.jsonl"

    def save(self, session: Session) -> Path:
        p = self._path(session.source, session.session_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for r in session.rounds:
                f.write(r.model_dump_json() + "\n")
        return p

    def read_rounds(self, source: str, session_id: str, start: int | None = None, end: int | None = None) -> list[Round]:
        p = self._path(source, session_id)
        if not p.exists():
            return []
        rounds = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rounds.append(Round.model_validate_json(line))
        if start is not None and end is not None:
            return rounds[start:end]
        elif start is not None:
            return rounds[start:]
        return rounds


class CardFiles:
    def __init__(self, base: Path):
        self.base = base

    def _path(self, card_id: str) -> Path:
        return self.base / card_id[:2] / f"{card_id}.json"

    def save(self, card_id: str, data: dict) -> Path:
        p = self._path(card_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        return p

    def read(self, card_id: str) -> dict | None:
        p = self._path(card_id)
        if not p.exists():
            return None
        return json.loads(p.read_text())
```

- [ ] **Step 5: storage/__init__.py**

```python
# memory_talk/storage/__init__.py
"""Storage layer."""
```

- [ ] **Step 6: Commit**

```bash
git add memory_talk/storage/ && git commit -m "feat: add storage layer (SQLite, LanceDB, files)"
```

---

### Task 5: TTL Service (service/ttl.py)

**Files:**
- Create: `memory_talk/service/__init__.py`
- Create: `memory_talk/service/ttl.py`

- [ ] **Step 1: TTL service**

```python
# memory_talk/service/__init__.py
"""Service layer."""

# memory_talk/service/ttl.py
"""TTL calculation — expires_at ↔ ttl conversion, factor-based refresh."""
from __future__ import annotations
import time
from memory_talk.config import TTLConfig


def compute_ttl(expires_at: float) -> int:
    """Convert expires_at to remaining seconds. Negative means expired."""
    return int(expires_at - time.time())


def initial_expires_at(cfg: TTLConfig) -> float:
    """Calculate expires_at for new object."""
    return time.time() + cfg.initial


def refresh_expires_at(current_expires_at: float, cfg: TTLConfig) -> float:
    """Refresh: remaining * factor, capped at max."""
    remaining = max(current_expires_at - time.time(), 1)  # at least 1 second
    new_remaining = min(remaining * cfg.factor, cfg.max)
    return time.time() + new_remaining
```

- [ ] **Step 2: Commit**

```bash
git add memory_talk/service/ && git commit -m "feat: add TTL service"
```

---

### Task 6: Service 层 — Sessions, Cards, Links, Recall (service/)

**Files:**
- Create: `memory_talk/service/sessions.py`
- Create: `memory_talk/service/cards.py`
- Create: `memory_talk/service/links.py`
- Create: `memory_talk/service/recall.py`

- [ ] **Step 1: sessions service**

```python
# memory_talk/service/sessions.py
"""Sessions service — import, list, read, tag."""
from __future__ import annotations
from memory_talk.config import Config
from memory_talk.models.session import Session
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.files import SessionFiles


class SessionsService:
    def __init__(self, config: Config):
        self.db = SQLiteStore(config.db_path)
        self.files = SessionFiles(config.sessions_dir)

    def import_session(self, session: Session) -> dict:
        self.files.save(session)
        synced_at = session.synced_at.isoformat() if session.synced_at else __import__("datetime").datetime.now().isoformat()
        self.db.save_session(
            session_id=session.session_id,
            source=session.source,
            metadata=session.metadata,
            tags=session.tags,
            round_count=len(session.rounds),
            synced_at=synced_at,
        )
        return {"status": "ok", "session_id": session.session_id, "rounds": len(session.rounds)}

    def list_sessions(self, tag: str | None = None) -> list[dict]:
        return self.db.list_sessions(tag=tag)

    def get_session(self, session_id: str, start: int | None = None, end: int | None = None) -> list[dict]:
        meta = self.db.get_session(session_id)
        if not meta:
            return []
        rounds = self.files.read_rounds(meta["source"], session_id, start=start, end=end)
        return [r.model_dump(mode="json") for r in rounds]

    def add_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.add_tags(session_id, tags)

    def remove_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.remove_tags(session_id, tags)
```

- [ ] **Step 2: cards service**

```python
# memory_talk/service/cards.py
"""Cards service — create, get, list."""
from __future__ import annotations
import time
from datetime import datetime
from ulid import ULID
from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.models.card import TalkCard, CardRound, CardLinkInput
from memory_talk.service.ttl import compute_ttl, initial_expires_at, refresh_expires_at
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.lancedb import LanceStore
from memory_talk.storage.files import CardFiles


class CardsService:
    def __init__(self, config: Config):
        self.config = config
        self.db = SQLiteStore(config.db_path)
        self.vectors = LanceStore(config.vectors_dir)
        self.files = CardFiles(config.cards_dir)
        self.embedder = get_embedder(config)

    def create(self, data: dict) -> dict:
        card_id = data.get("card_id") or str(ULID()).lower()
        now = datetime.now()
        expires_at = initial_expires_at(self.config.settings.ttl.card)

        # Build card file data
        card_data = {
            "card_id": card_id,
            "summary": data["summary"],
            "session_id": data.get("session_id"),
            "rounds": data.get("rounds", []),
            "links": data.get("links", []),
            "created_at": now.isoformat(),
        }

        # Save file
        self.files.save(card_id, card_data)

        # Save to SQLite
        self.db.save_card(card_id, data["summary"], data.get("session_id"), expires_at, now.isoformat())

        # Create links
        from memory_talk.service.links import LinksService
        links_svc = LinksService(self.config)
        for lk in data.get("links", []):
            links_svc.create({
                "source_id": card_id,
                "source_type": "card",
                "target_id": lk["id"],
                "target_type": lk["type"],
                "comment": lk.get("comment"),
            })

        # Embed
        text = f"{data['summary']}\n" + "\n".join(r.get("text", "") for r in data.get("rounds", []))
        embedding = self.embedder.embed_one(text)
        self.vectors.add(card_id, text, embedding)

        return {"status": "ok", "card_id": card_id}

    def get(self, card_id: str, link_id: str | None = None) -> dict | None:
        card_data = self.files.read(card_id)
        if not card_data:
            return None

        # Get TTL from SQLite
        db_card = self.db.get_card(card_id)
        if db_card:
            card_data["ttl"] = compute_ttl(db_card["expires_at"])

        # Get links
        links = self.db.get_links(card_id)
        card_data["links"] = [
            {
                "link_id": lk["link_id"],
                "id": lk["target_id"] if lk["source_id"] == card_id else lk["source_id"],
                "type": lk["target_type"] if lk["source_id"] == card_id else lk["source_type"],
                "comment": lk.get("comment"),
                "ttl": compute_ttl(lk["expires_at"]),
            }
            for lk in links
            if compute_ttl(lk["expires_at"]) > 0
        ]

        # Refresh link TTL if link_id provided
        if link_id:
            for lk in links:
                if lk["link_id"] == link_id:
                    new_exp = refresh_expires_at(lk["expires_at"], self.config.settings.ttl.link)
                    self.db.refresh_link_ttl(link_id, new_exp)
                    break

        return card_data

    def list_cards(self, session_id: str | None = None) -> list[dict]:
        rows = self.db.list_cards(session_id=session_id)
        return [{"card_id": r["card_id"], "summary": r["summary"], "session_id": r["session_id"], "ttl": compute_ttl(r["expires_at"])} for r in rows]
```

- [ ] **Step 3: links service**

```python
# memory_talk/service/links.py
"""Links service — create, list, delete."""
from __future__ import annotations
from datetime import datetime
from ulid import ULID
from memory_talk.config import Config
from memory_talk.service.ttl import compute_ttl, initial_expires_at
from memory_talk.storage.sqlite import SQLiteStore


class LinksService:
    def __init__(self, config: Config):
        self.config = config
        self.db = SQLiteStore(config.db_path)

    def create(self, data: dict) -> dict:
        link_id = str(ULID()).lower()
        now = datetime.now()
        expires_at = initial_expires_at(self.config.settings.ttl.link)
        self.db.save_link(
            link_id=link_id,
            source_id=data["source_id"],
            source_type=data["source_type"],
            target_id=data["target_id"],
            target_type=data["target_type"],
            comment=data.get("comment"),
            expires_at=expires_at,
            created_at=now.isoformat(),
        )
        return {"status": "ok", "link_id": link_id}

    def list_links(self, obj_id: str, type_filter: str | None = None) -> list[dict]:
        rows = self.db.get_links(obj_id, type_filter=type_filter)
        return [
            {
                "link_id": r["link_id"],
                "source_id": r["source_id"],
                "source_type": r["source_type"],
                "target_id": r["target_id"],
                "target_type": r["target_type"],
                "comment": r["comment"],
                "ttl": compute_ttl(r["expires_at"]),
            }
            for r in rows
        ]

    def delete(self, link_id: str) -> dict:
        ok = self.db.delete_link(link_id)
        return {"status": "ok" if ok else "not_found"}
```

- [ ] **Step 4: recall service**

```python
# memory_talk/service/recall.py
"""Recall service — vector search with TTL refresh."""
from __future__ import annotations
from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.service.ttl import compute_ttl, refresh_expires_at
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.lancedb import LanceStore
from memory_talk.storage.files import CardFiles


class RecallService:
    def __init__(self, config: Config):
        self.config = config
        self.db = SQLiteStore(config.db_path)
        self.vectors = LanceStore(config.vectors_dir)
        self.files = CardFiles(config.cards_dir)
        self.embedder = get_embedder(config)

    def recall(self, query: str, top_k: int = 5) -> dict:
        embedding = self.embedder.embed_one(query)
        hits = self.vectors.search(embedding, top_k=top_k)

        results = []
        for hit in hits:
            card_id = hit["card_id"]
            db_card = self.db.get_card(card_id)
            if not db_card:
                continue

            ttl = compute_ttl(db_card["expires_at"])
            if ttl <= 0:
                continue

            # Refresh card TTL on recall
            new_exp = refresh_expires_at(db_card["expires_at"], self.config.settings.ttl.card)
            self.db.refresh_card_ttl(card_id, new_exp)

            # Get active links
            links_raw = self.db.get_links(card_id)
            links = [
                {
                    "link_id": lk["link_id"],
                    "id": lk["target_id"] if lk["source_id"] == card_id else lk["source_id"],
                    "type": lk["target_type"] if lk["source_id"] == card_id else lk["source_type"],
                    "comment": lk["comment"],
                    "ttl": compute_ttl(lk["expires_at"]),
                }
                for lk in links_raw
                if compute_ttl(lk["expires_at"]) > 0
            ]

            results.append({
                "card_id": card_id,
                "summary": db_card["summary"],
                "session_id": db_card["session_id"],
                "ttl": compute_ttl(new_exp),
                "distance": hit["distance"],
                "links": links,
            })

        return {"query": query, "results": results, "count": len(results)}
```

- [ ] **Step 5: Commit**

```bash
git add memory_talk/service/ && git commit -m "feat: add service layer (sessions, cards, links, recall)"
```

---

### Task 7: Adapters (adapters/)

**Files:**
- Create: `memory_talk/adapters/__init__.py`
- Create: `memory_talk/adapters/base.py`
- Create: `memory_talk/adapters/claude_code.py`

- [ ] **Step 1: Base + Claude Code adapter**

```python
# memory_talk/adapters/__init__.py
"""Platform adapters."""

# memory_talk/adapters/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from memory_talk.models.session import Session


class Adapter(ABC):
    name: str

    @abstractmethod
    def discover(self) -> list[Path]:
        ...

    @abstractmethod
    def convert(self, source_path: Path) -> Session:
        ...
```

```python
# memory_talk/adapters/claude_code.py
"""Claude Code adapter — reads ~/.claude/projects/ JSONL."""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from memory_talk.adapters.base import Adapter
from memory_talk.models.session import Session, Round, TextBlock, ThinkingBlock


CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"

    def __init__(self, projects_dir: Path | None = None):
        self.projects_dir = projects_dir or CLAUDE_PROJECTS

    def discover(self) -> list[Path]:
        if not self.projects_dir.exists():
            return []
        paths = []
        for project in sorted(self.projects_dir.iterdir()):
            if project.is_dir():
                paths.extend(sorted(project.glob("*.jsonl")))
        return paths

    def convert(self, source_path: Path) -> Session:
        rounds = []
        first_ts = None
        with open(source_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type")
                if msg_type not in ("user", "assistant"):
                    continue
                ts = self._parse_ts(data.get("timestamp", ""))
                if first_ts is None and ts:
                    first_ts = ts
                blocks = self._parse_content(data, msg_type)
                if not blocks:
                    continue
                rounds.append(Round(
                    round_id=data.get("uuid", f"r{i:04d}"),
                    parent_id=data.get("parentUuid"),
                    timestamp=ts,
                    speaker=msg_type,
                    role="human" if msg_type == "user" else "assistant",
                    content=blocks,
                    is_sidechain=data.get("isSidechain", False),
                    cwd=data.get("cwd"),
                ))
        return Session(
            session_id=source_path.stem,
            source=self.name,
            created_at=first_ts,
            metadata={"project": self._decode_project(source_path.parent.name), "source_path": str(source_path)},
            rounds=rounds,
            round_count=len(rounds),
        )

    def _parse_content(self, data, msg_type):
        blocks = []
        msg = data.get("message", {})
        if msg_type == "user":
            raw = msg.get("content", "")
            text = raw if isinstance(raw, str) else json.dumps(raw)
            if text:
                blocks.append(TextBlock(text=text))
        elif msg_type == "assistant":
            parts = msg.get("content", [])
            if isinstance(parts, str):
                if parts:
                    blocks.append(TextBlock(text=parts))
            elif isinstance(parts, list):
                for p in parts:
                    if not isinstance(p, dict):
                        continue
                    pt = p.get("type")
                    if pt == "text" and p.get("text"):
                        blocks.append(TextBlock(text=p["text"]))
                    elif pt == "thinking" and p.get("thinking"):
                        blocks.append(ThinkingBlock(thinking=p["thinking"]))
                    elif pt == "tool_use":
                        blocks.append(TextBlock(text=f"[{p.get('name', 'tool')}] {json.dumps(p.get('input', ''))}"))
        return blocks

    def _parse_ts(self, s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _decode_project(self, name):
        user = os.getenv("USER") or os.getenv("USERNAME", "")
        prefix = f"-home-{user}-"
        if name.startswith(prefix):
            return name.replace(prefix, f"/home/{user}/", 1).replace("-", "/")
        return name


ADAPTERS = {"claude-code": ClaudeCodeAdapter}

def get_adapter(name: str) -> Adapter:
    cls = ADAPTERS.get(name)
    if not cls:
        raise ValueError(f"Unknown adapter: {name}")
    return cls()
```

- [ ] **Step 2: Commit**

```bash
git add memory_talk/adapters/ && git commit -m "feat: add adapters (Claude Code)"
```

---

### Task 8: API 层 (api/)

**Files:**
- Create: `memory_talk/api/__init__.py`
- Create: `memory_talk/api/sessions.py`
- Create: `memory_talk/api/cards.py`
- Create: `memory_talk/api/links.py`
- Create: `memory_talk/api/recall.py`
- Create: `memory_talk/api/status.py`

- [ ] **Step 1: FastAPI app**

```python
# memory_talk/api/__init__.py
"""FastAPI application."""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from memory_talk.config import Config
from memory_talk.storage.init_db import init_db


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.ensure_dirs()
    init_db(config.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="memory.talk", lifespan=lifespan)
    app.state.config = config

    from memory_talk.api import sessions, cards, links, recall, status
    app.include_router(sessions.router)
    app.include_router(cards.router)
    app.include_router(links.router)
    app.include_router(recall.router)
    app.include_router(status.router)

    return app
```

- [ ] **Step 2: sessions API**

```python
# memory_talk/api/sessions.py
from __future__ import annotations
from fastapi import APIRouter, Request, Query
from memory_talk.models.session import Session
from memory_talk.service.sessions import SessionsService

router = APIRouter()

@router.post("/sessions")
def create_session(session: Session, request: Request):
    svc = SessionsService(request.app.state.config)
    return svc.import_session(session)

@router.get("/sessions")
def list_sessions(request: Request, tag: str | None = Query(None)):
    svc = SessionsService(request.app.state.config)
    return svc.list_sessions(tag=tag)

@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request, start: int | None = Query(None), end: int | None = Query(None)):
    svc = SessionsService(request.app.state.config)
    return svc.get_session(session_id, start=start, end=end)

@router.post("/sessions/{session_id}/tags")
def add_tags(session_id: str, request: Request, body: dict):
    svc = SessionsService(request.app.state.config)
    svc.add_tags(session_id, body.get("tags", []))
    return {"status": "ok"}

@router.delete("/sessions/{session_id}/tags")
def remove_tags(session_id: str, request: Request, body: dict):
    svc = SessionsService(request.app.state.config)
    svc.remove_tags(session_id, body.get("tags", []))
    return {"status": "ok"}
```

- [ ] **Step 3: cards API**

```python
# memory_talk/api/cards.py
from __future__ import annotations
from fastapi import APIRouter, Request, Query

router = APIRouter()

@router.post("/cards")
def create_card(body: dict, request: Request):
    from memory_talk.service.cards import CardsService
    svc = CardsService(request.app.state.config)
    return svc.create(body)

@router.get("/cards")
def list_cards(request: Request, session_id: str | None = Query(None)):
    from memory_talk.service.cards import CardsService
    svc = CardsService(request.app.state.config)
    return svc.list_cards(session_id=session_id)

@router.get("/cards/{card_id}")
def get_card(card_id: str, request: Request, link_id: str | None = Query(None)):
    from memory_talk.service.cards import CardsService
    svc = CardsService(request.app.state.config)
    result = svc.get(card_id, link_id=link_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Card not found")
    return result
```

- [ ] **Step 4: links API**

```python
# memory_talk/api/links.py
from __future__ import annotations
from fastapi import APIRouter, Request, Query
from memory_talk.models.link import LinkCreate

router = APIRouter()

@router.post("/links")
def create_link(body: LinkCreate, request: Request):
    from memory_talk.service.links import LinksService
    svc = LinksService(request.app.state.config)
    return svc.create(body.model_dump())

@router.get("/links")
def list_links(request: Request, id: str = Query(...), type: str | None = Query(None)):
    from memory_talk.service.links import LinksService
    svc = LinksService(request.app.state.config)
    return svc.list_links(id, type_filter=type)

@router.delete("/links/{link_id}")
def delete_link(link_id: str, request: Request):
    from memory_talk.service.links import LinksService
    svc = LinksService(request.app.state.config)
    return svc.delete(link_id)
```

- [ ] **Step 5: recall + status API**

```python
# memory_talk/api/recall.py
from __future__ import annotations
from fastapi import APIRouter, Request
from pydantic import BaseModel

class RecallRequest(BaseModel):
    query: str
    top_k: int = 5

router = APIRouter()

@router.post("/recall")
def recall(body: RecallRequest, request: Request):
    from memory_talk.service.recall import RecallService
    svc = RecallService(request.app.state.config)
    return svc.recall(body.query, body.top_k)
```

```python
# memory_talk/api/status.py
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/status")
def status(request: Request):
    from memory_talk.storage.sqlite import SQLiteStore
    config = request.app.state.config
    db = SQLiteStore(config.db_path)
    return {
        "sessions_total": db.count_sessions(),
        "cards_total": db.count_cards(),
        "links_total": db.count_links(),
        "vector_provider": config.settings.vector.provider,
        "relation_provider": config.settings.relation.provider,
        "embedding_provider": config.settings.embedding.provider,
    }
```

- [ ] **Step 6: Commit**

```bash
git add memory_talk/api/ && git commit -m "feat: add FastAPI API layer"
```

---

### Task 9: CLI (cli.py)

**Files:**
- Create: `memory_talk/cli.py`

- [ ] **Step 1: CLI 实现**

```python
# memory_talk/cli.py
"""CLI entry point — manages server and calls API."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time
import hashlib
from pathlib import Path

import click
import httpx

from memory_talk.config import Config

BASE_URL = "http://127.0.0.1:7788"


def _config(data_root: str | None) -> Config:
    return Config(data_root) if data_root else Config()


def _api(method: str, path: str, **kwargs) -> dict:
    """Call local API server."""
    try:
        r = httpx.request(method, f"{BASE_URL}{path}", timeout=30, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        click.echo(json.dumps({"error": "Server not running. Run 'memory-talk server start' first."}), err=True)
        raise SystemExit(1)


@click.group()
@click.version_option()
def main():
    """memory-talk: Persistent cross-session memory for AI agents."""
    pass


# --- server ---

@main.group()
def server():
    """Manage local API server."""
    pass


@server.command()
@click.option("--data-root", default=None, type=click.Path())
@click.option("--port", default=7788, type=int)
def start(data_root: str | None, port: int):
    """Start the API server as a background process."""
    config = _config(data_root)
    config.ensure_dirs()

    if config.pid_path.exists():
        pid = int(config.pid_path.read_text().strip())
        try:
            os.kill(pid, 0)
            click.echo(json.dumps({"status": "already_running", "pid": pid}))
            return
        except OSError:
            config.pid_path.unlink()

    env = os.environ.copy()
    if data_root:
        env["MEMORY_TALK_DATA_ROOT"] = str(data_root)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "memory_talk.api:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    config.pid_path.write_text(str(proc.pid))
    time.sleep(1)
    click.echo(json.dumps({"status": "started", "pid": proc.pid, "port": port}))


@server.command()
@click.option("--data-root", default=None, type=click.Path())
def stop(data_root: str | None):
    """Stop the API server."""
    config = _config(data_root)
    if not config.pid_path.exists():
        click.echo(json.dumps({"status": "not_running"}))
        return
    pid = int(config.pid_path.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        config.pid_path.unlink()
        click.echo(json.dumps({"status": "stopped", "pid": pid}))
    except OSError:
        config.pid_path.unlink()
        click.echo(json.dumps({"status": "not_running"}))


@server.command("status")
@click.option("--data-root", default=None, type=click.Path())
def server_status(data_root: str | None):
    """Check server status."""
    config = _config(data_root)
    if not config.pid_path.exists():
        click.echo(json.dumps({"status": "not_running"}))
        return
    pid = int(config.pid_path.read_text().strip())
    try:
        os.kill(pid, 0)
        click.echo(json.dumps({"status": "running", "pid": pid}))
    except OSError:
        config.pid_path.unlink()
        click.echo(json.dumps({"status": "not_running"}))


# --- sync ---

@main.command()
@click.option("--data-root", default=None, type=click.Path())
def sync(data_root: str | None):
    """Sync conversations from all platforms."""
    config = _config(data_root)
    from memory_talk.adapters.claude_code import ClaudeCodeAdapter
    from memory_talk.storage.sqlite import SQLiteStore
    from memory_talk.storage.init_db import init_db

    config.ensure_dirs()
    init_db(config.db_path)
    db = SQLiteStore(config.db_path)

    adapter = ClaudeCodeAdapter()
    all_paths = adapter.discover()
    stats = {"name": "claude", "sessions_total": 0, "sessions_new": 0, "sessions_updated": 0, "rounds_new": 0}

    for path in all_paths:
        stats["sessions_total"] += 1
        file_hash = _file_hash(path)
        if db.is_ingested(str(path), file_hash):
            continue
        session = adapter.convert(path)
        # POST to API
        try:
            _api("POST", "/sessions", json=session.model_dump(mode="json"))
            db.log_ingest(str(path), session.session_id, file_hash, __import__("datetime").datetime.now().isoformat())
            stats["sessions_new"] += 1
            stats["rounds_new"] += len(session.rounds)
        except SystemExit:
            raise
        except Exception:
            pass

    click.echo(json.dumps({"platforms": [stats], "total": {"sessions": stats["sessions_total"], "new": stats["sessions_new"], "updated": stats["sessions_updated"], "rounds_new": stats["rounds_new"]}}, indent=2))


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# --- sessions ---

@main.group()
def sessions():
    """Manage sessions."""
    pass

@sessions.command("list")
@click.option("--tag", default=None)
def sessions_list(tag: str | None):
    click.echo(json.dumps(_api("GET", "/sessions", params={"tag": tag} if tag else {}), indent=2, default=str))

@sessions.command()
@click.argument("session_id")
@click.option("--start", default=None, type=int)
@click.option("--end", default=None, type=int)
def read(session_id: str, start: int | None, end: int | None):
    params = {}
    if start is not None: params["start"] = start
    if end is not None: params["end"] = end
    click.echo(json.dumps(_api("GET", f"/sessions/{session_id}", params=params), indent=2, default=str))

@sessions.group()
def tag():
    """Manage session tags."""
    pass

@tag.command("add")
@click.argument("session_id")
@click.argument("tags", nargs=-1)
def tag_add(session_id: str, tags: tuple):
    click.echo(json.dumps(_api("POST", f"/sessions/{session_id}/tags", json={"tags": list(tags)})))

@tag.command("remove")
@click.argument("session_id")
@click.argument("tags", nargs=-1)
def tag_remove(session_id: str, tags: tuple):
    click.echo(json.dumps(_api("DELETE", f"/sessions/{session_id}/tags", json={"tags": list(tags)})))


# --- cards ---

@main.group()
def cards():
    """Manage Talk-Cards."""
    pass

@cards.command()
@click.argument("card_json")
def create(card_json: str):
    data = json.loads(card_json)
    click.echo(json.dumps(_api("POST", "/cards", json=data), indent=2))

@cards.command()
@click.argument("card_id")
@click.option("--link-id", default=None)
def get(card_id: str, link_id: str | None):
    params = {"link_id": link_id} if link_id else {}
    click.echo(json.dumps(_api("GET", f"/cards/{card_id}", params=params), indent=2, default=str))

@cards.command("list")
@click.option("--session-id", default=None)
def cards_list(session_id: str | None):
    params = {"session_id": session_id} if session_id else {}
    click.echo(json.dumps(_api("GET", "/cards", params=params), indent=2, default=str))


# --- links ---

@main.group()
def links():
    """Manage links."""
    pass

@links.command()
@click.argument("link_json")
def create(link_json: str):
    data = json.loads(link_json)
    click.echo(json.dumps(_api("POST", "/links", json=data), indent=2))

@links.command("list")
@click.argument("id")
@click.option("--type", "type_", default=None)
def links_list(id: str, type_: str | None):
    params = {"id": id}
    if type_: params["type"] = type_
    click.echo(json.dumps(_api("GET", "/links", params=params), indent=2, default=str))


# --- recall ---

@main.command()
@click.argument("query")
@click.option("--top-k", default=5, type=int)
def recall(query: str, top_k: int):
    click.echo(json.dumps(_api("POST", "/recall", json={"query": query, "top_k": top_k}), indent=2, default=str))


# --- status ---

@main.command()
def status():
    click.echo(json.dumps(_api("GET", "/status"), indent=2))
```

- [ ] **Step 2: API module-level app for uvicorn**

Add to `memory_talk/api/__init__.py` at bottom:

```python
# Module-level app for uvicorn
import os
from memory_talk.config import Config

_data_root = os.environ.get("MEMORY_TALK_DATA_ROOT")
app = create_app(Config(_data_root) if _data_root else Config())
```

- [ ] **Step 3: Commit**

```bash
git add memory_talk/cli.py memory_talk/api/__init__.py && git commit -m "feat: add CLI with server management"
```

---

### Task 10: 场景测试

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_story_01_database.py`
- Create: `tests/test_story_02_bug.py`
- Create: `tests/test_story_03_recall.py`

- [ ] **Step 1: conftest.py**

```python
# tests/__init__.py
# (empty)

# tests/conftest.py
"""Test fixtures — temp data root, API client, fake sessions."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, Client

from memory_talk.api import create_app
from memory_talk.config import Config
from memory_talk.storage.init_db import init_db


@pytest.fixture
def temp_root():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def config(temp_root):
    c = Config(temp_root)
    c.ensure_dirs()
    c.save()
    init_db(c.db_path)
    return c


@pytest.fixture
def client(config):
    app = create_app(config)
    transport = ASGITransport(app=app)
    with Client(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def fake_claude_sessions(temp_root):
    """Create fake Claude Code JSONL files."""
    projects = temp_root / "claude_projects" / "testproject"
    projects.mkdir(parents=True)

    # Session 1: database decision (20 rounds, condensed to key ones)
    s1 = projects / "sess_db_decision.jsonl"
    lines = [
        json.dumps({"type": "user", "uuid": "u001", "parentUuid": None, "timestamp": "2026-04-10T10:00:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "我们需要一个向量数据库，ChromaDB 和 LanceDB 你怎么看？"}}),
        json.dumps({"type": "assistant", "uuid": "a001", "parentUuid": "u001", "timestamp": "2026-04-10T10:00:05Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "关键考量是部署形态——Skill 嵌入式场景不能要求用户启动额外服务"}, {"type": "text", "text": "ChromaDB 功能成熟但需要独立服务进程。LanceDB 是嵌入式方案，零依赖，数据就是本地文件。"}]}}),
        json.dumps({"type": "user", "uuid": "u002", "parentUuid": "a001", "timestamp": "2026-04-10T10:01:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "就用 LanceDB，零依赖这点太重要了。"}}),
    ]
    s1.write_text("\n".join(lines) + "\n")

    # Session 2: bug investigation (simplified)
    s2 = projects / "sess_bug_investigation.jsonl"
    lines = [
        json.dumps({"type": "user", "uuid": "b001", "parentUuid": None, "timestamp": "2026-04-11T09:00:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "memory-talk cards create 有时候会卡住，大概 10 秒不返回"}}),
        json.dumps({"type": "assistant", "uuid": "b002", "parentUuid": "b001", "timestamp": "2026-04-11T09:00:05Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "卡住而非报错，说明不是异常而是阻塞"}, {"type": "text", "text": "加了计时日志后发现卡在 _ensure_table 方法。怀疑是表创建的开销。"}]}}),
        json.dumps({"type": "assistant", "uuid": "b003", "parentUuid": "b002", "timestamp": "2026-04-11T09:05:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "text", "text": "找到了。LanceDB create_table 在 NFS 上会触发 fsync，网络文件系统上很慢。"}]}}),
        json.dumps({"type": "user", "uuid": "b004", "parentUuid": "b003", "timestamp": "2026-04-11T09:05:30Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "我确实是在 NFS 上跑的，公司的开发机。"}}),
        json.dumps({"type": "assistant", "uuid": "b005", "parentUuid": "b004", "timestamp": "2026-04-11T09:06:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "text", "text": "修复方案：首次 sync 时预创建 LanceDB 表和 schema。"}]}}),
    ]
    s2.write_text("\n".join(lines) + "\n")

    return projects
```

- [ ] **Step 2: test_story_01_database.py**

```python
# tests/test_story_01_database.py
"""Story 01: 数据库选型的记忆 — sync → read → cards create → recall"""
import json
from memory_talk.adapters.claude_code import ClaudeCodeAdapter


class TestDatabaseDecision:

    def test_full_story(self, client, config, fake_claude_sessions):
        # 1. Import session via adapter → POST /sessions
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        paths = adapter.discover()
        db_session_path = [p for p in paths if "db_decision" in p.name][0]
        session = adapter.convert(db_session_path)

        r = client.post("/sessions", json=session.model_dump(mode="json"))
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        session_id = r.json()["session_id"]

        # 2. List sessions
        r = client.get("/sessions")
        assert r.status_code == 200
        sessions = r.json()
        assert len(sessions) >= 1
        assert any(s["session_id"] == session_id for s in sessions)

        # 3. Read session rounds
        r = client.get(f"/sessions/{session_id}")
        assert r.status_code == 200
        rounds = r.json()
        assert len(rounds) == 3

        # 4. Create card (simplified rounds, link to session)
        card_data = {
            "summary": "项目选定 LanceDB 作为向量存储方案，主要原因是零依赖、嵌入式架构",
            "session_id": session_id,
            "rounds": [
                {"role": "human", "text": "我们需要一个向量数据库，ChromaDB 和 LanceDB 你怎么看？"},
                {"role": "assistant", "text": "LanceDB 零依赖，嵌入式方案，适合 Skill 场景。", "thinking": "关键考量是部署形态"},
                {"role": "human", "text": "就用 LanceDB。"},
            ],
            "links": [
                {"id": session_id, "type": "session", "comment": "从这段数据库选型讨论中提取"},
            ],
        }
        r = client.post("/cards", json=card_data)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        card_id = r.json()["card_id"]

        # 5. Recall
        r = client.post("/recall", json={"query": "数据库选型 LanceDB", "top_k": 5})
        assert r.status_code == 200
        recall_data = r.json()
        assert recall_data["count"] >= 1
        found = [c for c in recall_data["results"] if c["card_id"] == card_id]
        assert len(found) == 1
        assert found[0]["ttl"] > 0
        assert len(found[0]["links"]) >= 1

        # 6. Status
        r = client.get("/status")
        assert r.status_code == 200
        st = r.json()
        assert st["sessions_total"] >= 1
        assert st["cards_total"] >= 1
```

- [ ] **Step 3: test_story_02_bug.py**

```python
# tests/test_story_02_bug.py
"""Story 02: Bug 排查的记忆 — sync → cards create with links → verify"""
from memory_talk.adapters.claude_code import ClaudeCodeAdapter


class TestBugInvestigation:

    def test_full_story(self, client, config, fake_claude_sessions):
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        paths = adapter.discover()

        # Import both sessions
        for path in paths:
            session = adapter.convert(path)
            client.post("/sessions", json=session.model_dump(mode="json"))

        # Create card for database decision first
        sessions = client.get("/sessions").json()
        db_session = [s for s in sessions if "db_decision" in s["session_id"]][0]
        bug_session = [s for s in sessions if "bug" in s["session_id"]][0]

        card1_r = client.post("/cards", json={
            "summary": "选定 LanceDB 做向量存储",
            "session_id": db_session["session_id"],
            "rounds": [{"role": "human", "text": "ChromaDB vs LanceDB?"}, {"role": "assistant", "text": "用 LanceDB"}],
            "links": [{"id": db_session["session_id"], "type": "session"}],
        })
        card1_id = card1_r.json()["card_id"]

        # Create bug card with link to session AND link to card1
        card2_r = client.post("/cards", json={
            "summary": "cards create 偶发卡死——LanceDB 在 NFS 上首次建表会阻塞",
            "session_id": bug_session["session_id"],
            "rounds": [
                {"role": "human", "text": "cards create 有时候会卡住"},
                {"role": "assistant", "text": "卡在 _ensure_table，LanceDB 在 NFS 上 fsync 慢", "thinking": "卡住不是报错，是阻塞"},
                {"role": "assistant", "text": "修复：预创建表结构"},
            ],
            "links": [
                {"id": bug_session["session_id"], "type": "session", "comment": "bug 排查过程"},
                {"id": card1_id, "type": "card", "comment": "LanceDB 选型的后果"},
            ],
        })
        card2_id = card2_r.json()["card_id"]

        # Verify links
        links = client.get("/links", params={"id": card2_id}).json()
        assert len(links) == 2
        link_types = {lk["target_type"] for lk in links}
        assert "session" in link_types
        assert "card" in link_types

        # Verify card get
        card = client.get(f"/cards/{card2_id}").json()
        assert card["summary"] == "cards create 偶发卡死——LanceDB 在 NFS 上首次建表会阻塞"
        assert len(card["rounds"]) == 3
        assert card["ttl"] > 0
```

- [ ] **Step 4: test_story_03_recall.py**

```python
# tests/test_story_03_recall.py
"""Story 03: 一次意外的回忆 — recall → links → TTL refresh"""
import time
from memory_talk.adapters.claude_code import ClaudeCodeAdapter


class TestRecallAndConnect:

    def test_full_story(self, client, config, fake_claude_sessions):
        # Setup: import sessions and create both cards (same as story 1+2)
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        for path in adapter.discover():
            session = adapter.convert(path)
            client.post("/sessions", json=session.model_dump(mode="json"))

        sessions = client.get("/sessions").json()
        db_sid = [s for s in sessions if "db_decision" in s["session_id"]][0]["session_id"]
        bug_sid = [s for s in sessions if "bug" in s["session_id"]][0]["session_id"]

        card1 = client.post("/cards", json={
            "summary": "选定 LanceDB 做向量存储，零依赖嵌入式方案",
            "session_id": db_sid,
            "rounds": [{"role": "human", "text": "ChromaDB vs LanceDB?"}, {"role": "assistant", "text": "用 LanceDB"}],
            "links": [{"id": db_sid, "type": "session"}],
        }).json()
        card1_id = card1["card_id"]

        card2 = client.post("/cards", json={
            "summary": "LanceDB 在 NFS 上首次建表阻塞，需预创建表结构",
            "session_id": bug_sid,
            "rounds": [{"role": "human", "text": "cards create 卡住"}, {"role": "assistant", "text": "NFS 上 fsync 慢"}],
            "links": [
                {"id": bug_sid, "type": "session"},
                {"id": card1_id, "type": "card", "comment": "选型的后果"},
            ],
        }).json()
        card2_id = card2["card_id"]

        # 1. Recall "ChromaDB 选型" — should find both cards
        recall_r = client.post("/recall", json={"query": "ChromaDB 选型 LanceDB", "top_k": 5}).json()
        assert recall_r["count"] >= 1

        # Record initial card TTL
        card1_before = client.get(f"/cards/{card1_id}").json()
        initial_ttl = card1_before["ttl"]

        # 2. Recall again — card TTL should have been refreshed (expires_at pushed forward)
        time.sleep(0.1)  # tiny delay so time progresses
        recall_r2 = client.post("/recall", json={"query": "LanceDB 向量存储", "top_k": 5}).json()
        card1_after = client.get(f"/cards/{card1_id}").json()
        # TTL should be >= initial because recall refreshed it
        assert card1_after["ttl"] >= initial_ttl

        # 3. Cards get with --link-id → link TTL refreshed
        links = client.get("/links", params={"id": card2_id}).json()
        card_link = [lk for lk in links if lk["target_type"] == "card"][0]
        link_id = card_link["link_id"]
        link_ttl_before = card_link["ttl"]

        time.sleep(0.1)
        client.get(f"/cards/{card2_id}", params={"link_id": link_id})

        links_after = client.get("/links", params={"id": card2_id}).json()
        card_link_after = [lk for lk in links_after if lk["link_id"] == link_id][0]
        assert card_link_after["ttl"] >= link_ttl_before

        # 4. Status check
        st = client.get("/status").json()
        assert st["sessions_total"] == 2
        assert st["cards_total"] == 2
        assert st["links_total"] >= 3  # 2 session links + 1 card link
```

- [ ] **Step 5: Commit**

```bash
git add tests/ && git commit -m "feat: add scenario tests matching stories/s1/"
```

---

### Task 11: 安装 + 运行测试

- [ ] **Step 1: 安装依赖**

```bash
pip install -e ".[dev]" --break-system-packages --no-cache-dir
```

- [ ] **Step 2: 运行所有测试**

```bash
pytest tests/ -v
```

Expected: All 3 story tests pass.

- [ ] **Step 3: 修复失败的测试（如有）**

迭代修复直到全部通过。

- [ ] **Step 4: Final commit**

```bash
git add -A && git commit -m "fix: all story tests passing"
git push
```
