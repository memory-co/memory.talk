# memory.talk v2 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay down the v2 skeleton — directory structure, ID system, storage schema additions, dated jsonl writer, Pydantic models, and a mandatory embedding-provider startup check — on top of which subsequent v2 plans (writes, reads, ops, CLI) will build.

**Architecture:** v2 lives in a single `memory_talk/v2/` subpackage (models, ids, storage, logging utilities, future services), a `memory_talk/api/v2/` FastAPI router package mounted at `/v2`, and a `memory_talk/cli/v2.py` Click CLI module discovered via the existing `MEMORY_TALK_CLI_VERSION=v2` dispatcher. v2 data (sessions/cards/links/logs) sits in the same `~/.memory-talk/` data root but under a different SQLite schema namespace and different file layout from v1 — no data migration attempted.

**Tech Stack:** Python 3.10+, Pydantic v2, FastAPI, Click, SQLite, LanceDB, pytest. Same deps as v1 (see `pyproject.toml`).

**Pre-requisites:**
- Specs are already written. All data / API / CLI behavior is documented in `docs/structure/v2/`, `docs/cli/v2/`, and `docs/api/v2/`. This plan implements that spec — when in doubt, read those docs.
- Create a worktree for v2 work: `git worktree add ../memory.talk-v2 -b feat/v2-foundation` before starting. All subsequent tasks run in that worktree.

---

## File Structure

### New files
- `memory_talk/v2/__init__.py` — subpackage marker
- `memory_talk/v2/ids.py` — ID generation and validation (`card_` / `sess_` / `link_` prefixes)
- `memory_talk/v2/models.py` — Pydantic models for v2 (Session, Card, Link, SearchLog, etc.)
- `memory_talk/v2/logging.py` — dated jsonl writer (`logs/search/<YYYY-MM-DD>.jsonl`, `logs/events/<YYYY-MM-DD>.jsonl`)
- `memory_talk/v2/storage/__init__.py` — subpackage marker
- `memory_talk/v2/storage/schema.py` — new SQLite tables (search_log, event_log) + init function
- `memory_talk/api/v2/__init__.py` — FastAPI router aggregator (empty for now, mounted by api root)
- `memory_talk/api/v2/status.py` — `GET /v2/status` endpoint
- `memory_talk/cli/v2.py` — Click CLI module (for now: only `server start/stop/status`)
- `tests/v1/__init__.py` — package marker (new, after restructure)
- `tests/v2/__init__.py` — package marker
- `tests/v2/test_ids.py` — ID prefix / generation tests
- `tests/v2/test_logging.py` — dated jsonl writer tests
- `tests/v2/test_storage.py` — SQLite schema init tests
- `tests/v2/test_embedding_startup_check.py` — embedding validation tests
- `tests/v2/test_cli_server.py` — v2 server smoke tests

### Modified files
- `memory_talk/config.py` — add `SearchConfig` pydantic model and wire into `Settings`
- `memory_talk/embedding.py` — add `validate_embedder(config)` function + `health_check()` hook on each `Embedder` subclass
- `memory_talk/api/__init__.py` — mount `/v2` router; call `validate_embedder` in lifespan
- `memory_talk/cli/__init__.py` — no change (v2 dispatcher already works via env var)
- `pyproject.toml` — no change (reusing same deps)

### Moved files (Task 1 restructure)
- `tests/base/` → `tests/v1/base/`
- `tests/scenario/` → `tests/v1/scenario/`
- `tests/server/` → `tests/v1/server/`
- `tests/conftest.py` → `tests/v1/conftest.py`
- `tests/README.md` → `tests/v1/README.md`

And 5 call-sites updated to import `tests.v1.conftest` instead of `tests.conftest`:
- `tests/v1/base/rebuild/test_rebuild.py`
- `tests/v1/scenario/01_database_decision/test_database_decision.py`
- `tests/v1/scenario/02_bug_investigation/test_bug_investigation.py`
- `tests/v1/scenario/03_recall_and_connect/test_recall_and_connect.py`
- `tests/v1/scenario/04_search/test_search.py`

---

## Task 1: Worktree + restructure tests into v1/v2 layout

**Why first:** All subsequent tasks put new tests in `tests/v2/`. Before we create that directory, we should get existing v1 tests into `tests/v1/` so the two layers are clearly separated and can share neither conftest nor fixtures unintentionally. Doing this as a single pre-work commit keeps the diff clean: the move is one commit, real v2 code starts in the next commit.

**Files:**
- Move: `tests/base/` → `tests/v1/base/` (with `git mv`)
- Move: `tests/scenario/` → `tests/v1/scenario/`
- Move: `tests/server/` → `tests/v1/server/`
- Move: `tests/conftest.py` → `tests/v1/conftest.py`
- Move: `tests/README.md` → `tests/v1/README.md`
- Create: `tests/v1/__init__.py` (empty)
- Create: `tests/v2/__init__.py` (empty)
- Modify (imports): 5 test files that currently `from tests.conftest import ...`

- [ ] **Step 1: Create worktree (run once, outside the plan loop)**

```bash
cd /home/twwyzh/mem-go/memory.talk
git worktree add ../memory.talk-v2 -b feat/v2-foundation
cd ../memory.talk-v2
```

All following commands assume `cwd = ../memory.talk-v2`.

- [ ] **Step 2: Baseline — confirm v1 tests all pass before touching anything**

```bash
pytest tests/ -x --tb=short -q
```

Expected: 81 passed (or whatever the current count is — record it for comparison).

- [ ] **Step 3: Move v1 tests into `tests/v1/` with git mv**

```bash
mkdir tests/v1 tests/v2
git mv tests/base tests/v1/base
git mv tests/scenario tests/v1/scenario
git mv tests/server tests/v1/server
git mv tests/conftest.py tests/v1/conftest.py
git mv tests/README.md tests/v1/README.md
touch tests/v1/__init__.py tests/v2/__init__.py
```

Verify the shape:

```bash
ls tests/        # expect: __init__.py  v1  v2
ls tests/v1/     # expect: README.md __init__.py base conftest.py scenario server
ls tests/v2/     # expect: __init__.py
```

- [ ] **Step 4: Update the 5 import call-sites that still say `from tests.conftest import ...`**

```bash
grep -rln "from tests.conftest" tests/v1/
```

Expected hits (5 files):
- `tests/v1/base/rebuild/test_rebuild.py`
- `tests/v1/scenario/01_database_decision/test_database_decision.py`
- `tests/v1/scenario/02_bug_investigation/test_bug_investigation.py`
- `tests/v1/scenario/03_recall_and_connect/test_recall_and_connect.py`
- `tests/v1/scenario/04_search/test_search.py`

Replace `from tests.conftest import` with `from tests.v1.conftest import` in each — use sed or an editor:

```bash
find tests/v1 -name "*.py" -exec sed -i 's|from tests\.conftest import|from tests.v1.conftest import|g' {} +
```

Re-verify:

```bash
grep -rln "from tests.conftest " tests/   # expect: (empty output)
grep -rln "from tests.v1.conftest " tests/v1/   # expect: 5 hits
```

- [ ] **Step 5: Run the full test suite — verify zero regressions**

```bash
pytest tests/ -x --tb=short -q
```

Expected: same count as baseline in Step 2 (e.g., 81 passed), no failures.

- [ ] **Step 6: Commit the restructure as a single reviewable commit**

```bash
git add tests/
git commit -m "test: move v1 tests into tests/v1, reserve tests/v2 for v2 suite"
```

---

## Task 2: Settings SearchConfig

**Files:**
- Modify: `memory_talk/config.py`
- Test: `tests/v2/test_settings_search.py` (new)

- [ ] **Step 1: Write failing test** for `SearchConfig` defaults

Create `tests/v2/test_settings_search.py`:

```python
from memory_talk.config import Config, Settings, SearchConfig


def test_search_config_defaults():
    sc = SearchConfig()
    assert sc.default_top_k == 10
    assert sc.comment_max_length == 500
    assert sc.search_log_retention_days == 0


def test_settings_has_search_section(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = Config(str(tmp_path / ".memory-talk"))
    assert cfg.settings.search.default_top_k == 10


def test_settings_search_override_from_json(tmp_path):
    data_root = tmp_path / ".memory-talk"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        '{"search": {"default_top_k": 20}}'
    )
    cfg = Config(str(data_root))
    assert cfg.settings.search.default_top_k == 20
    assert cfg.settings.search.comment_max_length == 500  # default preserved
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/v2/test_settings_search.py -v
```

Expected: ImportError or AttributeError (`SearchConfig` doesn't exist yet).

- [ ] **Step 4: Implement `SearchConfig` in `memory_talk/config.py`**

Add near the other Pydantic config classes:

```python
class SearchConfig(BaseModel):
    default_top_k: int = 10
    comment_max_length: int = 500
    search_log_retention_days: int = 0
```

Add `search: SearchConfig = SearchConfig()` field to the `Settings` model.

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/v2/test_settings_search.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add memory_talk/config.py tests/v2/__init__.py tests/v2/test_settings_search.py
git commit -m "feat(v2): add SearchConfig to settings"
```

---

## Task 3: ID prefix utilities

**Files:**
- Create: `memory_talk/v2/__init__.py` (empty)
- Create: `memory_talk/v2/ids.py`
- Test: `tests/v2/test_ids.py`

- [ ] **Step 1: Write failing test**

Create `tests/v2/test_ids.py`:

```python
import pytest
from memory_talk.v2.ids import (
    new_card_id, new_session_id, new_link_id,
    prefix_session_id, parse_id, IdKind, InvalidIdError,
)


def test_new_card_id_has_prefix():
    cid = new_card_id()
    assert cid.startswith("card_")
    assert len(cid) == len("card_") + 26  # ULID is 26 chars


def test_new_link_id_has_prefix():
    assert new_link_id().startswith("link_")


def test_new_session_id_from_platform_id():
    assert prefix_session_id("187c6576-875f") == "sess_187c6576-875f"


def test_prefix_session_id_is_idempotent():
    already = "sess_187c6576-875f"
    assert prefix_session_id(already) == already


def test_parse_id_card():
    assert parse_id("card_01jz8k2m0000000000000000") == (IdKind.CARD, "01jz8k2m0000000000000000")


def test_parse_id_session():
    assert parse_id("sess_abc123") == (IdKind.SESSION, "abc123")


def test_parse_id_link():
    assert parse_id("link_01jzq7rm0000000000000000") == (IdKind.LINK, "01jzq7rm0000000000000000")


def test_parse_id_invalid_prefix():
    with pytest.raises(InvalidIdError):
        parse_id("sch_xxx")


def test_parse_id_no_prefix():
    with pytest.raises(InvalidIdError):
        parse_id("01jz8k2m")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/v2/test_ids.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `memory_talk/v2/ids.py`**

```python
"""v2 ID utilities — prefix-based typed identifiers."""
from __future__ import annotations
from enum import Enum
from ulid import ULID


CARD_PREFIX = "card_"
SESSION_PREFIX = "sess_"
LINK_PREFIX = "link_"


class IdKind(str, Enum):
    CARD = "card"
    SESSION = "session"
    LINK = "link"


class InvalidIdError(ValueError):
    """Raised when an id string does not match any v2 prefix."""


def new_card_id() -> str:
    return f"{CARD_PREFIX}{ULID()}"


def new_link_id() -> str:
    return f"{LINK_PREFIX}{ULID()}"


def prefix_session_id(platform_id: str) -> str:
    """Prefix a raw platform session id with `sess_`. Idempotent."""
    if platform_id.startswith(SESSION_PREFIX):
        return platform_id
    return f"{SESSION_PREFIX}{platform_id}"


def parse_id(id_str: str) -> tuple[IdKind, str]:
    """Parse a prefixed id into (kind, raw_id). Raises InvalidIdError if no known prefix."""
    if id_str.startswith(CARD_PREFIX):
        return IdKind.CARD, id_str[len(CARD_PREFIX):]
    if id_str.startswith(SESSION_PREFIX):
        return IdKind.SESSION, id_str[len(SESSION_PREFIX):]
    if id_str.startswith(LINK_PREFIX):
        return IdKind.LINK, id_str[len(LINK_PREFIX):]
    raise InvalidIdError(f"id must start with {CARD_PREFIX!r}, {SESSION_PREFIX!r}, or {LINK_PREFIX!r}: got {id_str!r}")
```

Create `memory_talk/v2/__init__.py` as an empty file.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/v2/test_ids.py -v
```

Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_talk/v2/__init__.py memory_talk/v2/ids.py tests/v2/test_ids.py
git commit -m "feat(v2): add ID prefix utilities (card_/sess_/link_)"
```

---

## Task 4: Dated jsonl writer

**Files:**
- Create: `memory_talk/v2/logging.py`
- Test: `tests/v2/test_logging.py`

- [ ] **Step 1: Write failing test**

Create `tests/v2/test_logging.py`:

```python
import json
from datetime import datetime, timezone
from memory_talk.v2.logging import DatedJsonlWriter


def test_writer_creates_file_for_today(tmp_path):
    base = tmp_path / "logs" / "search"
    w = DatedJsonlWriter(base_dir=base)
    w.append({"search_id": "sch_a", "query": "x"}, now=datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc))
    assert (base / "2026-04-22.jsonl").exists()
    line = (base / "2026-04-22.jsonl").read_text().strip()
    assert json.loads(line) == {"search_id": "sch_a", "query": "x"}


def test_writer_appends_multiple_lines_same_day(tmp_path):
    base = tmp_path / "logs" / "search"
    w = DatedJsonlWriter(base_dir=base)
    d = datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc)
    w.append({"a": 1}, now=d)
    w.append({"b": 2}, now=d)
    content = (base / "2026-04-22.jsonl").read_text().strip().split("\n")
    assert [json.loads(l) for l in content] == [{"a": 1}, {"b": 2}]


def test_writer_splits_by_utc_day(tmp_path):
    base = tmp_path / "logs" / "events"
    w = DatedJsonlWriter(base_dir=base)
    w.append({"k": "x"}, now=datetime(2026, 4, 22, 23, 59, 59, tzinfo=timezone.utc))
    w.append({"k": "y"}, now=datetime(2026, 4, 23, 0, 0, 0, tzinfo=timezone.utc))
    assert (base / "2026-04-22.jsonl").exists()
    assert (base / "2026-04-23.jsonl").exists()


def test_writer_iter_files_sorted(tmp_path):
    base = tmp_path / "logs" / "events"
    w = DatedJsonlWriter(base_dir=base)
    for d in ["2026-04-21", "2026-04-20", "2026-04-22"]:
        (base / f"{d}.jsonl").parent.mkdir(parents=True, exist_ok=True)
        (base / f"{d}.jsonl").write_text("")
    files = list(w.iter_files())
    assert [f.name for f in files] == ["2026-04-20.jsonl", "2026-04-21.jsonl", "2026-04-22.jsonl"]


def test_writer_creates_base_dir_if_missing(tmp_path):
    base = tmp_path / "new" / "nested" / "dir"
    w = DatedJsonlWriter(base_dir=base)
    w.append({"x": 1})
    assert base.exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/v2/test_logging.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `memory_talk/v2/logging.py`**

```python
"""Dated jsonl writer for v2 audit logs (search, events)."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class DatedJsonlWriter:
    """Append-only jsonl writer that rotates files daily by UTC date.

    Layout: `<base_dir>/<YYYY-MM-DD>.jsonl`, one file per UTC day.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _file_for(self, now: datetime) -> Path:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)
        return self.base_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"

    def append(self, record: dict, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self._file_for(now)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")

    def iter_files(self) -> Iterator[Path]:
        """Yield jsonl files in chronological order (sorted by filename)."""
        if not self.base_dir.exists():
            return
        for p in sorted(self.base_dir.glob("*.jsonl")):
            yield p
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/v2/test_logging.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_talk/v2/logging.py tests/v2/test_logging.py
git commit -m "feat(v2): add dated jsonl writer for audit logs"
```

---

## Task 5: SQLite schema — search_log and event_log

**Files:**
- Create: `memory_talk/v2/storage/__init__.py` (empty)
- Create: `memory_talk/v2/storage/schema.py`
- Test: `tests/v2/test_storage.py`

- [ ] **Step 1: Write failing test**

Create `tests/v2/test_storage.py`:

```python
import sqlite3
from memory_talk.v2.storage.schema import init_v2_schema


def test_init_creates_search_log_table(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_log'").fetchall()
    assert len(rows) == 1


def test_search_log_columns(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(search_log)")}
    assert cols == {"search_id", "query", "where_dsl", "top_k", "created_at", "response_json"}


def test_init_creates_event_log_table(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_log'").fetchall()
    assert len(rows) == 1


def test_event_log_columns(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(event_log)")}
    assert cols == {"event_id", "object_id", "object_kind", "at", "kind", "detail_json"}


def test_init_is_idempotent(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    init_v2_schema(conn)  # should not raise
    rows = conn.execute("SELECT COUNT(*) FROM search_log").fetchone()
    assert rows[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/v2/test_storage.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `memory_talk/v2/storage/schema.py`**

```python
"""v2 SQLite schema additions (search_log, event_log).

v2 shares the same SQLite database file as v1. These tables are
v2-specific and do not interfere with v1's tables.
"""
from __future__ import annotations
import sqlite3


SEARCH_LOG_DDL = """
CREATE TABLE IF NOT EXISTS search_log (
    search_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    where_dsl TEXT,
    top_k INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    response_json TEXT NOT NULL
);
"""

EVENT_LOG_DDL = """
CREATE TABLE IF NOT EXISTS event_log (
    event_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
"""

EVENT_LOG_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_event_log_object
    ON event_log (object_id, at);
"""


def init_v2_schema(conn: sqlite3.Connection) -> None:
    """Create v2 tables if they don't exist. Idempotent."""
    conn.executescript(SEARCH_LOG_DDL)
    conn.executescript(EVENT_LOG_DDL)
    conn.executescript(EVENT_LOG_INDEX_DDL)
    conn.commit()
```

Create `memory_talk/v2/storage/__init__.py` as empty.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/v2/test_storage.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_talk/v2/storage/__init__.py memory_talk/v2/storage/schema.py tests/v2/test_storage.py
git commit -m "feat(v2): add search_log and event_log SQLite tables"
```

---

## Task 6: Embedding startup check (the user's explicit ask)

**Files:**
- Modify: `memory_talk/embedding.py`
- Modify: `memory_talk/api/__init__.py`
- Test: `tests/v2/test_embedding_startup_check.py`

- [ ] **Step 1: Write failing test**

Create `tests/v2/test_embedding_startup_check.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from memory_talk.config import Config
from memory_talk.embedding import validate_embedder, EmbedderValidationError


def test_dummy_validates(tmp_path):
    (tmp_path / "settings.json").write_text('{"embedding": {"provider": "dummy"}}')
    cfg = Config(str(tmp_path))
    # should not raise
    validate_embedder(cfg)


def test_openai_missing_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with pytest.raises(EmbedderValidationError, match="UNIT_TEST_KEY"):
        validate_embedder(cfg)


def test_openai_present_env_and_live_ping_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with patch("memory_talk.embedding.httpx.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 1024}]}
        mock_post.return_value = resp
        # should not raise
        validate_embedder(cfg)
        assert mock_post.called


def test_openai_live_ping_http_error(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with patch("memory_talk.embedding.httpx.post") as mock_post:
        mock_post.side_effect = httpx.ConnectError("network unreachable")
        with pytest.raises(EmbedderValidationError, match="network unreachable"):
            validate_embedder(cfg)


def test_openai_live_ping_dim_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_TEST_KEY", "sk-fake")
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "text-embedding-v4", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    with patch("memory_talk.embedding.httpx.post") as mock_post:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 384}]}  # wrong dim
        mock_post.return_value = resp
        with pytest.raises(EmbedderValidationError, match="dim mismatch"):
            validate_embedder(cfg)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/v2/test_embedding_startup_check.py -v
```

Expected: ImportError (`validate_embedder` doesn't exist).

- [ ] **Step 3: Implement `validate_embedder`**

Append to `memory_talk/embedding.py`:

```python
class EmbedderValidationError(RuntimeError):
    """Raised by validate_embedder(config) when the configured embedding
    provider cannot be used. Meant to be caught at startup and surfaced
    to the operator, not silently swallowed."""


def validate_embedder(config) -> None:
    """Validate the configured embedding provider at startup.

    - `dummy`: trivially OK.
    - `local`: attempt to load the sentence-transformers model (catches missing
      package / missing model / disk failure).
    - `openai`: require the auth env var to be set AND perform a one-shot
      probe embed to catch unreachable endpoints, bad model names, wrong
      `dim` in settings, etc.

    Raises EmbedderValidationError with a user-readable message if anything
    is off. Caller is responsible for presenting the error and exiting.
    """
    emb = config.settings.embedding
    p = emb.provider

    if p == "dummy":
        return

    if p == "local":
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
            _ = SentenceTransformer(emb.model)  # triggers download/load
        except Exception as e:  # pragma: no cover - network-ish
            raise EmbedderValidationError(
                f"local embedder failed to load model {emb.model!r}: {e}"
            ) from e
        return

    if p == "openai":
        api_key = os.environ.get(emb.auth_env_key or "")
        if not api_key:
            raise EmbedderValidationError(
                f"openai embedder: environment variable {emb.auth_env_key!r} is not set"
            )
        try:
            resp = httpx.post(
                emb.endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": emb.model, "input": ["ping"], "encoding_format": "float"},
                timeout=emb.timeout,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                raise EmbedderValidationError("openai embedder: probe response contained no data")
            probe_dim = len(data[0]["embedding"])
            if probe_dim != emb.dim:
                raise EmbedderValidationError(
                    f"openai embedder: dim mismatch — settings say {emb.dim}, endpoint returned {probe_dim}"
                )
        except EmbedderValidationError:
            raise
        except Exception as e:
            raise EmbedderValidationError(f"openai embedder: {e}") from e
        return

    raise EmbedderValidationError(f"unknown embedding provider: {p}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/v2/test_embedding_startup_check.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Wire into FastAPI lifespan**

Modify `memory_talk/api/__init__.py` — replace the empty lifespan with one that calls `validate_embedder`:

```python
"""FastAPI app root. Mounts versioned routers."""
from __future__ import annotations
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from memory_talk.config import Config
from memory_talk.embedding import validate_embedder, EmbedderValidationError
from memory_talk.storage.init_db import init_db
from memory_talk.v2.storage.schema import init_v2_schema


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.ensure_dirs()
    init_db(config.db_path)

    # Also install v2 tables into the same sqlite file.
    import sqlite3
    with sqlite3.connect(config.db_path) as _conn:
        init_v2_schema(_conn)

    # Fail-fast embedding check BEFORE we accept any traffic.
    try:
        validate_embedder(config)
    except EmbedderValidationError as e:
        # Print to stderr so the CLI spawning this server can surface it.
        print(f"[memory-talk] embedding startup check failed: {e}", file=sys.stderr)
        raise SystemExit(2) from e

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="memory.talk", lifespan=lifespan)
    app.state.config = config

    from memory_talk.api.v1 import router as v1_router
    app.include_router(v1_router, prefix="/v1")
    return app


_data_root = os.environ.get("MEMORY_TALK_DATA_ROOT")
app = create_app(Config(_data_root) if _data_root else Config())
```

- [ ] **Step 6: Add integration test** for create_app exiting on bad embedder config

Append to `tests/v2/test_embedding_startup_check.py`:

```python
def test_create_app_exits_on_missing_env(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)
    (tmp_path / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )
    cfg = Config(str(tmp_path))
    from memory_talk.api import create_app
    with pytest.raises(SystemExit) as excinfo:
        create_app(cfg)
    assert excinfo.value.code == 2
```

- [ ] **Step 7: Run the full test file to confirm**

```bash
pytest tests/v2/test_embedding_startup_check.py -v
```

Expected: 6 PASS.

- [ ] **Step 8: Also verify the existing v1 test suite still passes**

```bash
pytest tests/ -x --tb=short 2>&1 | tail -30
```

Expected: all green (no regressions).

- [ ] **Step 9: Commit**

```bash
git add memory_talk/embedding.py memory_talk/api/__init__.py tests/v2/test_embedding_startup_check.py
git commit -m "feat(v2): validate embedding provider at server startup"
```

---

## Task 7: v2 Pydantic models (shell only — fields covered by later plans)

**Files:**
- Create: `memory_talk/v2/models.py`
- Test: `tests/v2/test_models.py`

- [ ] **Step 1: Write failing test**

Create `tests/v2/test_models.py`:

```python
import pytest
from pydantic import ValidationError
from memory_talk.v2.models import LinkRef, SearchLog, EventLog


def test_link_ref_round_trip():
    lr = LinkRef(
        link_id="link_01jzq7rm",
        target_id="sess_abc123",
        target_type="session",
        comment=None,
        ttl=0,
    )
    d = lr.model_dump()
    assert d["link_id"] == "link_01jzq7rm"
    assert d["target_type"] == "session"


def test_link_ref_rejects_bad_type():
    with pytest.raises(ValidationError):
        LinkRef(
            link_id="link_x", target_id="sess_x", target_type="sidecar",
            comment=None, ttl=0,
        )


def test_search_log_minimal():
    sl = SearchLog(
        search_id="sch_01K",
        query="x",
        where=None,
        top_k=10,
        created_at="2026-04-22T00:00:00Z",
        cards={"count": 0, "results": []},
        sessions={"count": 0, "results": []},
    )
    assert sl.top_k == 10


def test_event_log_minimal():
    ev = EventLog(
        event_id="evt_01K",
        object_id="card_xxx",
        object_kind="card",
        at="2026-04-22T00:00:00Z",
        kind="created",
        detail={"summary": "x", "rounds": [], "default_links": [], "ttl_initial": 2592000},
    )
    assert ev.kind == "created"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/v2/test_models.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `memory_talk/v2/models.py`**

```python
"""v2 Pydantic models.

Minimal shell — only the shared types used across multiple v2 services
and the persisted log schemas. Request / response models for individual
endpoints live with their services (future plans).
"""
from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel


LinkTargetType = Literal["card", "session"]
ObjectKind = Literal["card", "session"]


class LinkRef(BaseModel):
    """A link as it appears in view/search responses (from the perspective of
    the object being read)."""
    link_id: str
    target_id: str
    target_type: LinkTargetType
    comment: str | None = None
    ttl: int  # seconds; 0 = default link sentinel; <0 = expired


class SearchLog(BaseModel):
    """Persisted full-response audit record for a /v2/search call."""
    search_id: str
    query: str
    where: str | None
    top_k: int
    created_at: str
    cards: dict[str, Any]
    sessions: dict[str, Any]


class EventLog(BaseModel):
    """Single row in event_log — the wire shape for /v2/log events."""
    event_id: str
    object_id: str  # prefixed id (card_* or sess_*)
    object_kind: ObjectKind
    at: str
    kind: str  # event kind (imported, rounds_appended, tag_added, linked, created, ...)
    detail: dict[str, Any]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/v2/test_models.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_talk/v2/models.py tests/v2/test_models.py
git commit -m "feat(v2): add shared Pydantic models (LinkRef, SearchLog, EventLog)"
```

---

## Task 8: /v2/status endpoint

**Files:**
- Create: `memory_talk/api/v2/__init__.py`
- Create: `memory_talk/api/v2/status.py`
- Modify: `memory_talk/api/__init__.py` (mount v2 router)
- Test: `tests/v2/test_status.py`

- [ ] **Step 1: Write failing test**

Create `tests/v2/test_status.py`:

```python
from fastapi.testclient import TestClient
from memory_talk.api import create_app
from memory_talk.config import Config


def test_v2_status_running(tmp_path):
    (tmp_path / "settings.json").write_text('{"embedding": {"provider": "dummy"}}')
    cfg = Config(str(tmp_path))
    app = create_app(cfg)
    client = TestClient(app)

    resp = client.get("/v2/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert "sessions_total" in data
    assert "cards_total" in data
    assert "links_total" in data
    assert "searches_total" in data
    assert data["data_root"] == str(tmp_path)
    assert data["embedding_provider"] == "dummy"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/v2/test_status.py -v
```

Expected: 404 (no /v2/status yet).

- [ ] **Step 3: Implement v2 status router**

Create `memory_talk/api/v2/status.py`:

```python
"""GET /v2/status — stats for the v2 layer.

Deliberately reads counts out of the v2 SQLite tables (falling back
to shared v1 tables for sessions/cards/links, which v2 will ingest
into in later plans).
"""
from __future__ import annotations
import sqlite3

from fastapi import APIRouter, Request

router = APIRouter()


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


@router.get("/status")
async def get_status(request: Request) -> dict:
    config = request.app.state.config
    with sqlite3.connect(config.db_path) as conn:
        sessions_total = _count(conn, "sessions")
        cards_total = _count(conn, "cards")
        links_total = _count(conn, "links")
        searches_total = _count(conn, "search_log")

    return {
        "data_root": str(config.data_root),
        "settings_path": str(config.settings_path),
        "status": "running",
        "sessions_total": sessions_total,
        "cards_total": cards_total,
        "links_total": links_total,
        "searches_total": searches_total,
        "vector_provider": config.settings.vector.provider,
        "relation_provider": config.settings.relation.provider,
        "embedding_provider": config.settings.embedding.provider,
    }
```

Create `memory_talk/api/v2/__init__.py`:

```python
"""v2 API router aggregator."""
from fastapi import APIRouter

from memory_talk.api.v2.status import router as status_router

router = APIRouter()
router.include_router(status_router)
```

- [ ] **Step 4: Mount v2 router in `memory_talk/api/__init__.py`**

In `create_app`, add after the v1 include:

```python
    from memory_talk.api.v2 import router as v2_router
    app.include_router(v2_router, prefix="/v2")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/v2/test_status.py -v
```

Expected: PASS.

- [ ] **Step 6: Confirm v1 tests still green**

```bash
pytest tests/ -x 2>&1 | tail -10
```

- [ ] **Step 7: Commit**

```bash
git add memory_talk/api/v2/__init__.py memory_talk/api/v2/status.py memory_talk/api/__init__.py tests/v2/test_status.py
git commit -m "feat(v2): add GET /v2/status endpoint"
```

---

## Task 9: v2 CLI skeleton (server + version dispatch)

**Files:**
- Create: `memory_talk/cli/v2.py`
- Test: `tests/v2/test_cli_server.py`

- [ ] **Step 1: Write failing test**

Create `tests/v2/test_cli_server.py`:

```python
from click.testing import CliRunner


def test_v2_cli_has_server_group(monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_CLI_VERSION", "v2")
    # Re-import to trigger dispatcher with v2 env
    import importlib
    import memory_talk.cli
    importlib.reload(memory_talk.cli)
    from memory_talk.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["server", "--help"])
    assert result.exit_code == 0
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output


def test_v2_cli_server_status_without_server(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_CLI_VERSION", "v2")
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    import memory_talk.cli
    importlib.reload(memory_talk.cli)
    from memory_talk.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["server", "status"])
    # No server running → exits cleanly with JSON output {"status": "not_running"}
    assert result.exit_code == 0
    assert "not_running" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/v2/test_cli_server.py -v
```

Expected: ImportError (no `cli/v2.py`).

- [ ] **Step 3: Implement `memory_talk/cli/v2.py`**

Model after `cli/v1.py` but keep it minimal for now — just the server group. Use the same process/pid mechanism v1 uses so the v1 `server status` would also see a v2 server running (they share the port).

```python
"""v2 CLI — Click commands for memory-talk v2.

Currently only the `server` group is wired. `search`, `view`, `log`,
`card`, `tag`, `link`, `sync`, `rebuild` land in follow-up plans.
"""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click
import httpx

from memory_talk.config import Config


__all__ = ["main"]


def _api(method: str, path: str, cfg: Config, **kwargs) -> dict:
    url = f"http://127.0.0.1:{cfg.settings.server.port}{path}"
    resp = httpx.request(method, url, timeout=30.0, **kwargs)
    resp.raise_for_status()
    return resp.json()


@click.group()
def main() -> None:
    """memory-talk v2 CLI."""


@main.group()
def server() -> None:
    """Manage the local API server."""


@server.command("start")
@click.option("--data-root", type=click.Path(), default=None)
def server_start(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    cfg.ensure_dirs()
    if cfg.pid_path.exists():
        pid = int(cfg.pid_path.read_text().strip())
        try:
            os.kill(pid, 0)
            click.echo(json.dumps({"status": "already_running", "pid": pid, "port": cfg.settings.server.port}))
            return
        except ProcessLookupError:
            cfg.pid_path.unlink()
    env = os.environ.copy()
    if data_root:
        env["MEMORY_TALK_DATA_ROOT"] = str(cfg.data_root)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "memory_talk.api:app",
         "--host", "127.0.0.1", "--port", str(cfg.settings.server.port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True,
    )
    # Wait a moment — if the embedding check fails the child exits with code 2.
    time.sleep(1.0)
    if proc.poll() is not None:
        err = (proc.stderr.read() or b"").decode(errors="replace")
        click.echo(json.dumps({"status": "failed", "exit_code": proc.returncode, "error": err.strip()}))
        sys.exit(1)
    cfg.pid_path.write_text(str(proc.pid))
    click.echo(json.dumps({"status": "started", "pid": proc.pid, "port": cfg.settings.server.port}))


@server.command("stop")
@click.option("--data-root", type=click.Path(), default=None)
def server_stop(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    if not cfg.pid_path.exists():
        click.echo(json.dumps({"status": "not_running"}))
        return
    pid = int(cfg.pid_path.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    cfg.pid_path.unlink(missing_ok=True)
    click.echo(json.dumps({"status": "stopped", "pid": pid}))


@server.command("status")
@click.option("--data-root", type=click.Path(), default=None)
def server_status(data_root: str | None) -> None:
    cfg = Config(data_root) if data_root else Config()
    try:
        data = _api("GET", "/v2/status", cfg)
        click.echo(json.dumps(data))
    except Exception:
        click.echo(json.dumps({
            "data_root": str(cfg.data_root),
            "settings_path": str(cfg.settings_path),
            "status": "not_running",
        }))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/v2/test_cli_server.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Manual smoke test — full round-trip**

Run these commands manually in the worktree:

```bash
MEMORY_TALK_CLI_VERSION=v2 memory-talk --help
MEMORY_TALK_CLI_VERSION=v2 memory-talk server start
curl -s http://127.0.0.1:7788/v2/status | python -m json.tool
MEMORY_TALK_CLI_VERSION=v2 memory-talk server stop
```

Expected: help lists `server`; `server start` returns JSON with status `started`; curl returns v2/status JSON with `status: running`; `server stop` returns `stopped`.

- [ ] **Step 6: Commit**

```bash
git add memory_talk/cli/v2.py tests/v2/test_cli_server.py
git commit -m "feat(v2): add v2 CLI skeleton with server group"
```

---

## Task 10: End-to-end embedding startup check via CLI

**Files:**
- Test: `tests/v2/test_cli_server.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/v2/test_cli_server.py`:

```python
def test_v2_server_start_fails_loudly_on_bad_embedding(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_CLI_VERSION", "v2")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)

    # Configure openai embedding with a missing env var — this should make
    # the spawned uvicorn process exit 2 at startup and the CLI should surface it.
    data_root = tmp_path / ".memory-talk"
    data_root.mkdir(parents=True)
    (data_root / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )

    import importlib
    import memory_talk.cli
    importlib.reload(memory_talk.cli)
    from memory_talk.cli import main
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(main, ["server", "start", "--data-root", str(data_root)])
    # CLI surfaces a failed server start with non-zero exit code + error payload.
    assert result.exit_code != 0
    assert "failed" in result.output
    assert "UNIT_TEST_KEY" in result.output
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/v2/test_cli_server.py::test_v2_server_start_fails_loudly_on_bad_embedding -v
```

Expected: PASS (the earlier Task 5 already wired this behavior end-to-end).

- [ ] **Step 3: Full test suite run**

```bash
pytest tests/ -x --tb=short 2>&1 | tail -30
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/v2/test_cli_server.py
git commit -m "test(v2): verify bad embedding config surfaces via CLI server start"
```

---

## Task 11: Wrap-up — PR-ready branch

- [ ] **Step 1: Rebase / check clean tree**

```bash
git status
git log --oneline main..HEAD
```

Expected: 7-8 commits, clean working tree, no uncommitted changes.

- [ ] **Step 2: Full test run**

```bash
pytest tests/ -v 2>&1 | tail -40
```

Expected: v1 tests all green, v2 tests all green, **zero** regressions.

- [ ] **Step 3: Push branch**

```bash
git push -u origin feat/v2-foundation
```

- [ ] **Step 4: (Optional) Open PR**

Only if the user asks — don't auto-open.

---

## Follow-up plans (not in this file)

After this plan lands, the remaining v2 work breaks into four more plans, to be written one at a time:

- **Plan B — Writes**: `POST /v2/sessions` (ingest, append-only, index assignment), `POST /v2/cards` (rounds expansion, default links, embedding), `POST /v2/links` (user link), `POST /v2/tags/{add,remove}` (session tags). Event log gets populated here.
- **Plan C — Reads**: `POST /v2/search` (hybrid FTS + vector + DSL, SearchLog full-response persistence), `POST /v2/view` (prefix-dispatched card/session read with link expansion and TTL refresh), `POST /v2/log` (event stream).
- **Plan D — Ops**: `POST /v2/rebuild` (jsonl replay), plus flesh-out of `/v2/status`, plus the sync CLI command's platform adapters hooked through to `/v2/sessions`.
- **Plan E — CLI**: the remaining memory-talk subcommands (`search`, `view`, `log`, `card`, `tag`, `link`, `sync`, `rebuild`) in `memory_talk/cli/v2.py`, mapping 1:1 to the API endpoints.

Each of those is its own ~8-task plan.
