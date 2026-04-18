# Session 目录结构改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Session 存储从单文件变目录（meta.json + rounds.jsonl），SQLite 变纯索引缓存，新增 rebuild 命令从文件重建索引。

**Architecture:** SessionFiles 改为写目录（meta.json + rounds.jsonl）。import_session 同时写 meta.json。tag 操作同步更新 meta.json。新增异步 rebuild 命令：删 SQLite + LanceDB，从文件扫描重建。

**Tech Stack:** Python, SQLite, LanceDB, Click, FastAPI

**Spec:** `docs/superpowers/specs/2026-04-18-session-directory-design.md`

---

### Task 1: 改造 SessionFiles — 目录结构

**Files:**
- Modify: `memory_talk/storage/files.py`

- [ ] **Step 1: 修改 SessionFiles**

将 `_path` 改为返回目录，新增 `save_meta`、`read_meta` 方法：

```python
# memory_talk/storage/files.py — SessionFiles 部分完整替换
class SessionFiles:
    def __init__(self, base: Path):
        self.base = base

    def _dir(self, source: str, session_id: str) -> Path:
        return self.base / source / session_id[:2] / session_id

    def _rounds_path(self, source: str, session_id: str) -> Path:
        return self._dir(source, session_id) / "rounds.jsonl"

    def _meta_path(self, source: str, session_id: str) -> Path:
        return self._dir(source, session_id) / "meta.json"

    def save(self, session: Session) -> Path:
        d = self._dir(session.source, session.session_id)
        d.mkdir(parents=True, exist_ok=True)
        # Write rounds
        with (d / "rounds.jsonl").open("w") as f:
            for r in session.rounds:
                f.write(r.model_dump_json() + "\n")
        # Write meta
        meta = {
            "session_id": session.session_id,
            "source": session.source,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "synced_at": session.synced_at.isoformat() if session.synced_at else None,
            "metadata": session.metadata,
            "tags": session.tags,
            "round_count": len(session.rounds),
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))
        return d

    def save_meta(self, source: str, session_id: str, meta: dict) -> None:
        p = self._meta_path(source, session_id)
        p.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))

    def read_meta(self, source: str, session_id: str) -> dict | None:
        p = self._meta_path(source, session_id)
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def read_rounds(
        self,
        source: str,
        session_id: str,
        start: int = 0,
        end: Optional[int] = None,
    ) -> list[Round]:
        p = self._rounds_path(source, session_id)
        if not p.exists():
            return []
        lines = p.read_text().strip().splitlines()
        subset = lines[start:end]
        return [Round.model_validate_json(line) for line in subset]

    def scan_all(self) -> list[dict]:
        """Scan all session directories and return their meta.json contents."""
        results = []
        if not self.base.exists():
            return results
        for source_dir in sorted(self.base.iterdir()):
            if not source_dir.is_dir():
                continue
            for hash_dir in sorted(source_dir.iterdir()):
                if not hash_dir.is_dir():
                    continue
                for session_dir in sorted(hash_dir.iterdir()):
                    if not session_dir.is_dir():
                        continue
                    meta_path = session_dir / "meta.json"
                    if meta_path.exists():
                        results.append(json.loads(meta_path.read_text()))
        return results
```

- [ ] **Step 2: Commit**

```bash
git add memory_talk/storage/files.py && git commit -m "refactor: SessionFiles to directory structure (meta.json + rounds.jsonl)"
```

---

### Task 2: 更新 SessionsService — tag 同步写文件

**Files:**
- Modify: `memory_talk/service/sessions.py`

- [ ] **Step 1: 更新 import_session 和 tag 操作**

import_session 不再需要单独写 meta（SessionFiles.save 已经写了）。tag 操作需要同步更新 meta.json：

```python
# memory_talk/service/sessions.py — 完整替换
"""Sessions service — import, list, read, tag."""
from __future__ import annotations
from datetime import datetime
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
        synced_at = session.synced_at.isoformat() if session.synced_at else datetime.now().isoformat()
        created_at = session.created_at.isoformat() if session.created_at else None
        self.db.save_session(
            session_id=session.session_id, source=session.source,
            metadata=session.metadata, tags=session.tags,
            round_count=len(session.rounds), created_at=created_at, synced_at=synced_at,
        )
        return {"status": "ok", "session_id": session.session_id, "rounds": len(session.rounds)}

    def list_sessions(self, source: str | None = None, tag: str | None = None) -> list[dict]:
        rows = self.db.list_sessions(source=source)
        if tag:
            rows = [r for r in rows if tag in r.get("tags", [])]
        return rows

    def get_session(self, session_id: str, start: int | None = None, end: int | None = None) -> list[dict]:
        meta = self.db.get_session(session_id)
        if not meta:
            return []
        rounds = self.files.read_rounds(meta["source"], session_id, start=start or 0, end=end)
        return [r.model_dump(mode="json") for r in rounds]

    def add_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.add_tags(session_id, tags)
        self._sync_tags_to_file(session_id)

    def remove_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.remove_tags(session_id, tags)
        self._sync_tags_to_file(session_id)

    def _sync_tags_to_file(self, session_id: str) -> None:
        """Read current tags from SQLite and write back to meta.json."""
        session_meta = self.db.get_session(session_id)
        if not session_meta:
            return
        file_meta = self.files.read_meta(session_meta["source"], session_id)
        if not file_meta:
            return
        file_meta["tags"] = session_meta.get("tags", [])
        self.files.save_meta(session_meta["source"], session_id, file_meta)
```

- [ ] **Step 2: Commit**

```bash
git add memory_talk/service/sessions.py && git commit -m "feat: sync tags to meta.json on add/remove"
```

---

### Task 3: 新增 rebuild service + CLI 命令

**Files:**
- Create: `memory_talk/service/rebuild.py`
- Modify: `memory_talk/cli.py`
- Modify: `memory_talk/api/__init__.py` (add rebuild endpoint)

- [ ] **Step 1: Create rebuild service**

```python
# memory_talk/service/rebuild.py
"""Rebuild SQLite + LanceDB from file system."""
from __future__ import annotations
import shutil
import threading
from datetime import datetime

from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.storage.files import SessionFiles, CardFiles
from memory_talk.storage.init_db import init_db
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.lancedb import LanceStore
from memory_talk.service.ttl import initial_expires_at


def rebuild_async(config: Config) -> None:
    """Run rebuild in a background thread."""
    t = threading.Thread(target=_rebuild, args=(config,), daemon=True)
    t.start()


def _rebuild(config: Config) -> dict:
    """Delete SQLite + LanceDB, then rebuild from files."""
    # 1. Delete
    if config.db_path.exists():
        config.db_path.unlink()
    if config.vectors_dir.exists():
        shutil.rmtree(config.vectors_dir)
    config.vectors_dir.mkdir(parents=True, exist_ok=True)

    # 2. Recreate
    init_db(config.db_path)
    db = SQLiteStore(config.db_path)
    vectors = LanceStore(config.vectors_dir)
    embedder = get_embedder(config)

    # 3. Rebuild sessions from meta.json files
    session_files = SessionFiles(config.sessions_dir)
    session_count = 0
    for meta in session_files.scan_all():
        db.save_session(
            session_id=meta["session_id"],
            source=meta["source"],
            metadata=meta.get("metadata", {}),
            tags=meta.get("tags", []),
            round_count=meta.get("round_count", 0),
            created_at=meta.get("created_at"),
            synced_at=meta.get("synced_at"),
        )
        session_count += 1

    # 4. Rebuild cards + links from card JSON files
    card_files = CardFiles(config.cards_dir)
    card_count = 0
    link_count = 0
    for card_data in card_files.scan_all():
        card_id = card_data["card_id"]
        expires_at = initial_expires_at(config.settings.ttl.card)
        db.save_card(card_id, card_data["summary"], card_data.get("session_id"), expires_at, card_data.get("created_at", datetime.now().isoformat()))
        card_count += 1

        # Rebuild links
        from ulid import ULID
        for lk in card_data.get("links", []):
            link_id = str(ULID()).lower()
            link_expires = initial_expires_at(config.settings.ttl.link)
            db.save_link(
                link_id=link_id,
                source_id=card_id,
                source_type="card",
                target_id=lk["id"],
                target_type=lk["type"],
                comment=lk.get("comment"),
                expires_at=link_expires,
                created_at=card_data.get("created_at", datetime.now().isoformat()),
            )
            link_count += 1

        # Rebuild embedding
        text = f"{card_data['summary']}\n" + "\n".join(r.get("text", "") for r in card_data.get("rounds", []))
        embedding = embedder.embed_one(text)
        vectors.add(card_id, text, embedding)

    return {"status": "ok", "sessions": session_count, "cards": card_count, "links": link_count}


def rebuild_sync(config: Config) -> dict:
    """Synchronous rebuild — for testing."""
    return _rebuild(config)
```

- [ ] **Step 2: Add CardFiles.scan_all()**

Add to `memory_talk/storage/files.py` in the `CardFiles` class:

```python
    def scan_all(self) -> list[dict]:
        """Scan all card JSON files."""
        results = []
        if not self.base.exists():
            return results
        for hash_dir in sorted(self.base.iterdir()):
            if not hash_dir.is_dir():
                continue
            for card_file in sorted(hash_dir.glob("*.json")):
                results.append(json.loads(card_file.read_text()))
        return results
```

- [ ] **Step 3: Add rebuild CLI command**

Add to `memory_talk/cli.py` after the status command:

```python
@main.command()
@_fmt_option
def rebuild(fmt):
    """Rebuild SQLite + LanceDB index from files. Runs async."""
    from memory_talk.config import Config
    from memory_talk.service.rebuild import rebuild_async
    config = Config()
    rebuild_async(config)
    _output({"status": "rebuilding"}, fmt)
```

- [ ] **Step 4: Add rebuild API endpoint**

Create or add to `memory_talk/api/status.py`:

```python
@router.post("/rebuild")
def rebuild(request: Request):
    from memory_talk.service.rebuild import rebuild_async
    rebuild_async(request.app.state.config)
    return {"status": "rebuilding"}
```

- [ ] **Step 5: Commit**

```bash
git add memory_talk/service/rebuild.py memory_talk/storage/files.py memory_talk/cli.py memory_talk/api/status.py && git commit -m "feat: add rebuild command (async, from files)"
```

---

### Task 4: 更新测试

**Files:**
- Modify: all test files that create/use sessions
- Create: `tests/base/rebuild/` directory

- [ ] **Step 1: Update conftest**

The `load_sessions_from_dir` helper still returns `.jsonl` files from the test's `sessions/` directory. These are Claude Code JSONL files (adapter input), not memory.talk session files. This doesn't need to change — the adapter converts them and the service writes the new directory structure.

No changes to conftest.py needed.

- [ ] **Step 2: Create rebuild test**

```bash
mkdir -p tests/base/rebuild
touch tests/base/rebuild/__init__.py
```

```python
# tests/base/rebuild/test_rebuild.py
"""Test rebuild: delete SQLite, rebuild from files, verify data restored."""
import json
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from memory_talk.adapters.claude_code import ClaudeCodeAdapter
from memory_talk.api import create_app
from memory_talk.config import Config
from memory_talk.service.rebuild import rebuild_sync
from memory_talk.storage.init_db import init_db
from tests.conftest import load_sessions_from_dir

SESSIONS_DIR = Path(__file__).parent / "sessions"


@pytest.fixture
def fake_claude_sessions(temp_root):
    src = Path(__file__).parent.parent.parent / "scenario" / "01_database_decision" / "sessions"
    dst = temp_root / "claude_projects" / "testproject"
    shutil.copytree(src, dst)
    return dst


class TestRebuild:
    def test_rebuild_restores_sessions_and_cards(self, client, config, fake_claude_sessions):
        # 1. Import a session and create a card
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        for path in adapter.discover():
            session = adapter.convert(path)
            client.post("/sessions", json=session.model_dump(mode="json"))

        sessions_before = client.get("/sessions").json()
        assert len(sessions_before) >= 1
        session_id = sessions_before[0]["session_id"]

        client.post("/cards", json={
            "summary": "选定 LanceDB",
            "session_id": session_id,
            "rounds": [{"role": "human", "text": "test"}],
            "links": [{"id": session_id, "type": "session"}],
        })

        cards_before = client.get("/cards").json()
        assert len(cards_before) >= 1

        # 2. Delete SQLite
        config.db_path.unlink()

        # 3. Rebuild (sync for test)
        result = rebuild_sync(config)
        assert result["status"] == "ok"
        assert result["sessions"] >= 1
        assert result["cards"] >= 1

        # 4. Recreate client with rebuilt db
        app = create_app(config)
        with TestClient(app) as new_client:
            sessions_after = new_client.get("/sessions").json()
            assert len(sessions_after) == len(sessions_before)

            cards_after = new_client.get("/cards").json()
            assert len(cards_after) == len(cards_before)

            # Recall should work (LanceDB rebuilt)
            recall = new_client.post("/recall", json={"query": "LanceDB", "top_k": 5}).json()
            assert recall["count"] >= 1
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests pass (existing + new rebuild test).

- [ ] **Step 4: Commit**

```bash
git add tests/base/rebuild/ && git commit -m "test: add rebuild scenario test"
```

---

### Task 5: 更新文档

**Files:**
- Modify: `docs/structure/session.md`
- Create: `docs/cli/rebuild.md`
- Modify: `docs/cli/README.md`

- [ ] **Step 1: Update session.md storage path**

Update the directory structure example in `docs/structure/session.md` from:
```
sessions/{source}/{id[0:2]}/{session_id}.jsonl
```
to:
```
sessions/{source}/{id[0:2]}/{session_id}/
├── meta.json
└── rounds.jsonl
```

- [ ] **Step 2: Create rebuild.md**

```markdown
# rebuild

从文件系统重建 SQLite 索引和 LanceDB 向量库。异步执行。

```bash
memory-talk rebuild
```

删除 SQLite 和 LanceDB，从 sessions/ 和 cards/ 目录扫描重建。TTL 重置为默认 initial 值。

输出：
```json
{"status": "rebuilding"}
```
```

- [ ] **Step 3: Update CLI README**

Add `rebuild` to the command tree.

- [ ] **Step 4: Commit**

```bash
git add docs/ && git commit -m "docs: update session directory structure, add rebuild"
```
