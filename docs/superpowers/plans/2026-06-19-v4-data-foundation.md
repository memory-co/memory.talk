# v4 Card — Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v4 card subsystem's data layer — Pydantic models, prefixed ids, the 5-table SQLite schema, and the file-canonical + SQLite repository stores — with directory-based scenario tests modelled on `memorytalk/tests/searchbase/local/`.

**Architecture:** v4 lives in `v4/` subpackages alongside the existing (soon-to-be-`insight`) v3 code, mirroring the `docs/{cli,api,structure,works}/v4/` layout. The card is a *governed question graph*: one Card = one Issue (`issue`), several Positions (`claim`) competing by computed credence, connected by `card_links` (IBIS edges) and traced by `card_sessions` (provenance). This plan builds only the data layer: models + DDL + stores. SQLite is a derived index over file-canonical truth (`card.json` / `positions/<pid>.json`); **no FOREIGN KEYs** anywhere. credence is **computed at read/sort time in the service** (next plan), never stored — these stores only keep raw counts.

**Tech Stack:** Python 3.11, Pydantic v2 (`BaseModel`, never dataclass), `aiosqlite`, `python-ulid`, pytest + `asyncio_mode=auto`. File I/O via `memorytalk.provider.storage`.

---

## v4 Roadmap (this plan = Plan 1 of 6)

Each plan produces working, testable software on its own. Later plans are written when we reach them (decisions noted inline).

| # | Plan | Scope | Key open decision |
|---|---|---|---|
| **1** | **Data foundation** (this doc) | models, ids, 5-table DDL, repository stores | — |
| 2 | Migration | migration `v3` (rename v3 card→insight, free `card`/`cards`/`reviews`) + migration `v4` (create v4 tables, wire DDL into runner) | one-shot id-rewrite vs two-stage defer (see `docs/works/v4/insight-migration.md §5`) |
| 3 | Searchbase | `cards`(embed issue) + `positions`(embed claim) collections; upsert-on-create | — |
| 4 | Service | `CardService` (create card / add position / review / link / session) + read/recall/search (credence computed here) | credence formula: `up−down` (default) vs Wilson (`docs/works/v4/card.md §12`) |
| 5 | API | `/v4` FastAPI routers (cards, positions, reviews, card-links, card-sessions, read, search, recall) | — |
| 6 | CLI | `memory.talk card {create,position,review,link}`, `read`, `search`, `recall`, `insight` | — |

**Contract source of truth:** `docs/structure/v4/{card,review,card-link,card-session,filesystem}.md`, `docs/works/v4/card.md`. Field names below are copied from those docs.

---

## File Structure (Plan 1)

**Source (create):**
- `memorytalk/schemas/v4/__init__.py` — package marker
- `memorytalk/schemas/v4/card.py` — `Card`, `Position`, `CardLink`, `CardSession` read models + value types
- `memorytalk/schemas/v4/requests.py` — create request/response models
- `memorytalk/repository/v4/__init__.py` — package marker
- `memorytalk/repository/v4/schema.py` — the 5-table DDL (SQL constants), reused by migration `v4` init + tests
- `memorytalk/repository/v4/cards.py` — `V4CardStore`
- `memorytalk/repository/v4/positions.py` — `PositionStore`
- `memorytalk/repository/v4/reviews.py` — `V4ReviewStore`
- `memorytalk/repository/v4/links.py` — `CardLinkStore`
- `memorytalk/repository/v4/sessions.py` — `CardSessionStore`

**Source (modify):**
- `memorytalk/util/ids.py` — add `POSITION_PREFIX` / `new_position_id()` + `pos_` in `parse_id`

**Tests (create) — scenario dirs, each `{README.md, __init__.py, test.py}`:**
- `memorytalk/tests/repository/__init__.py`
- `memorytalk/tests/repository/v4/__init__.py`
- `memorytalk/tests/repository/v4/conftest.py` — `v4store` fixture (temp sqlite + v4 DDL + stores)
- `memorytalk/tests/repository/v4/schema/` — DDL: tables + columns exist, no FK
- `memorytalk/tests/repository/v4/cards/` — card row + file round-trip, counter bumps, list
- `memorytalk/tests/repository/v4/positions/` — position row + file round-trip, argument bump, list_for_card
- `memorytalk/tests/repository/v4/reviews/` — review insert + list_for_position + count
- `memorytalk/tests/repository/v4/links/` — link insert (target_type derive), idempotent dedup, list_out/in
- `memorytalk/tests/repository/v4/sessions/` — card_session insert, list_for_card, reverse lookup
- `memorytalk/tests/util/v4_ids/` — pos_ id mint + parse

**Conventions to follow (from the existing codebase):**
- Stores take `(conn: aiosqlite.Connection, storage: Storage)` (or just `conn` for relation-only stores), `await self.conn.commit()` after each write method.
- Bucket = `card_id[len("card_"):][:2].lower()` (see `repository/cards.py:_bucket`). For positions, bucket by their owning `card_id`.
- File layout: `cards/<bucket>/<card_id>/card.json`, `cards/<bucket>/<card_id>/positions/<position_id>.json`.
- Tests are `async def`, no `@pytest.mark.asyncio` needed (`asyncio_mode=auto`).
- JSON dumped with `ensure_ascii=False`.

---

### Task 1: v4 SQLite DDL + test fixture

**Files:**
- Create: `memorytalk/repository/v4/__init__.py` (empty)
- Create: `memorytalk/repository/v4/schema.py`
- Create: `memorytalk/tests/repository/__init__.py` (empty)
- Create: `memorytalk/tests/repository/v4/__init__.py` (empty)
- Create: `memorytalk/tests/repository/v4/conftest.py`
- Create: `memorytalk/tests/repository/v4/schema/__init__.py` (empty)
- Create: `memorytalk/tests/repository/v4/schema/README.md`
- Test: `memorytalk/tests/repository/v4/schema/test.py`

- [ ] **Step 1: Write the DDL module**

`memorytalk/repository/v4/schema.py`:

```python
"""v4 card subsystem SQLite schema (DDL constants).

Single source of truth for the 5 v4 tables. Reused by
``migrations/v4/init_database.py`` and by tests. SQLite is a derived
index over file-canonical truth (card.json / positions/<pid>.json);
**no FOREIGN KEY** anywhere (this repo's hard rule — dangling refs are
tolerated). Counters (position_count / link_count / up/down/neutral/
review_count) are redundant caches maintained on write. credence is NOT
a column — the service computes it at read/sort time.
"""
from __future__ import annotations

import aiosqlite

V4_TABLES: list[str] = [
    # Card ≡ Issue. position_count / link_count are redundant counters.
    """CREATE TABLE IF NOT EXISTS cards (
        card_id        TEXT PRIMARY KEY,
        issue          TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        position_count INTEGER NOT NULL DEFAULT 0,
        link_count     INTEGER NOT NULL DEFAULT 0
    )""",
    # Position = answer candidate. up/down/neutral_count = argument tallies;
    # review_count = up+down+neutral (redundant cache). scope = 位 (soft text);
    # forked_from_position_id = 变 (lineage). No credence column.
    """CREATE TABLE IF NOT EXISTS positions (
        position_id             TEXT PRIMARY KEY,
        card_id                 TEXT NOT NULL,
        claim                   TEXT NOT NULL,
        created_at              TEXT NOT NULL,
        up_count                INTEGER NOT NULL DEFAULT 0,
        down_count              INTEGER NOT NULL DEFAULT 0,
        neutral_count           INTEGER NOT NULL DEFAULT 0,
        review_count            INTEGER NOT NULL DEFAULT 0,
        scope                   TEXT NOT NULL DEFAULT '',
        forked_from_position_id TEXT
    )""",
    # Review = a stance on a Position. argument in {-1,0,1}. card_id is a
    # redundant cache (= positions.card_id; never drifts) so "all reviews for
    # this card" needs no join (works §8 / structure review.md).
    """CREATE TABLE IF NOT EXISTS reviews (
        review_id   TEXT PRIMARY KEY,
        position_id TEXT NOT NULL,
        card_id     TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        indexes     TEXT NOT NULL,
        argument    INTEGER NOT NULL,
        comment     TEXT,
        created_at  TEXT NOT NULL
    )""",
    # card↔card IBIS edge. card_id = subject (NOT from/to). target_type
    # ('card'|'position') derived from target_id prefix, stored for filtering.
    """CREATE TABLE IF NOT EXISTS card_links (
        card_id     TEXT NOT NULL,
        type        TEXT NOT NULL,
        target_id   TEXT NOT NULL,
        target_type TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (card_id, type, target_id)
    )""",
    # card↔session provenance (multi-session). No own id. position_id ''
    # = card-level association. PK (card_id, session_id, position_id): one
    # session can inspire a card and several of its positions (works §8 /
    # structure card-session.md).
    """CREATE TABLE IF NOT EXISTS card_sessions (
        card_id     TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        position_id TEXT NOT NULL DEFAULT '',
        indexes     TEXT NOT NULL DEFAULT '[]',
        created_at  TEXT NOT NULL,
        PRIMARY KEY (card_id, session_id, position_id)
    )""",
]

V4_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_v4_cards_created ON cards(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_v4_positions_card ON positions(card_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_reviews_position ON reviews(position_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_v4_reviews_card ON reviews(card_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_links_target ON card_links(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_v4_csess_session ON card_sessions(session_id)",
]


async def create_v4_schema(conn: aiosqlite.Connection) -> None:
    """Create all v4 tables + indexes (idempotent)."""
    for stmt in V4_TABLES:
        await conn.execute(stmt)
    for stmt in V4_INDEXES:
        await conn.execute(stmt)
    await conn.commit()
```

- [ ] **Step 2: Write the test conftest**

`memorytalk/tests/repository/v4/conftest.py`:

```python
"""Shared fixtures for v4 repository scenarios.

``v4db`` gives a temp SQLite (v4 DDL applied, row_factory=Row) plus a
LocalStorage file root. Each scenario constructs the store(s) it needs
from ``v4db.conn`` / ``v4db.storage`` via a small per-scenario fixture —
keeping scenarios decoupled so each store task is independently testable
(no scenario imports a store it doesn't use).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from memorytalk.config import Config
from memorytalk.provider.storage import LocalStorage
from memorytalk.repository.store import SQLiteStore
from memorytalk.repository.v4.schema import create_v4_schema


@pytest.fixture
async def v4db(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    conn = await SQLiteStore.open_connection(config.db_path)  # sets row_factory=Row
    await create_v4_schema(conn)
    storage = LocalStorage(config.data_root)
    try:
        yield SimpleNamespace(conn=conn, storage=storage)
    finally:
        await conn.close()
```

> Notes verified against the codebase: `data_root` comes from the top-level `memorytalk/tests/conftest.py` (temp dir + dummy-embedder settings.json). `memorytalk/provider/storage.py` exports `LocalStorage` (concrete) with `write_text` / `read_text` / `append_text`. `SQLiteStore.open_connection` sets `conn.row_factory = aiosqlite.Row` and `PRAGMA foreign_keys = ON` (fine — v4 declares no FKs).

- [ ] **Step 3: Write the failing schema test**

`memorytalk/tests/repository/v4/schema/test.py`:

```python
"""schema — v4 DDL creates the 5 tables with the right columns. See README.md."""
from __future__ import annotations


async def _columns(conn, table):
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        return {row["name"] for row in await cur.fetchall()}


async def test_five_tables_exist(v4db):
    async with v4db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cur:
        names = {r["name"] for r in await cur.fetchall()}
    assert {"cards", "positions", "reviews", "card_links", "card_sessions"} <= names


async def test_cards_has_redundant_counters(v4db):
    cols = await _columns(v4db.conn, "cards")
    assert {"card_id", "issue", "created_at", "position_count", "link_count"} == cols


async def test_positions_has_counts_and_governance(v4db):
    cols = await _columns(v4db.conn, "positions")
    assert {"up_count", "down_count", "neutral_count", "review_count",
            "scope", "forked_from_position_id"} <= cols
    assert "credence" not in cols  # credence is computed, never stored


async def test_card_links_has_target_type(v4db):
    cols = await _columns(v4db.conn, "card_links")
    assert {"card_id", "type", "target_id", "target_type"} <= cols


async def test_reviews_columns(v4db):
    cols = await _columns(v4db.conn, "reviews")
    assert {"review_id", "position_id", "card_id", "session_id",
            "indexes", "argument", "comment", "created_at"} == cols


async def test_card_sessions_columns(v4db):
    cols = await _columns(v4db.conn, "card_sessions")
    assert {"card_id", "session_id", "position_id", "indexes", "created_at"} == cols
```

- [ ] **Step 4: Write the scenario README**

`memorytalk/tests/repository/v4/schema/README.md`:

```markdown
# schema — v4 DDL shape

## 这个场景在测什么
`create_v4_schema` 建出 5 张表(cards / positions / reviews / card_links /
card_sessions),且列名跟 `docs/structure/v4/` 对齐:cards 带冗余计数
position_count/link_count;positions 带 up/down/neutral/review_count + scope +
forked_from_position_id,且 **没有 credence 列**(现算);card_links 带 target_type。

## 不在这测什么
- 各 store 的读写 round-trip → 各自场景目录
- 迁移 runner 接线 → Plan 2

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — 临时 SQLite + v4 DDL + LocalStorage(`.conn` / `.storage`)
```

- [ ] **Step 5: Run the test — expect pass once stores import-resolve**

Run: `pytest memorytalk/tests/repository/v4/schema/test.py -v`
Expected: 4 PASS. The `v4db` fixture only imports `schema.py`, so this task is fully self-contained — no dependency on the store tasks.

- [ ] **Step 6: Commit**

```bash
git add memorytalk/repository/v4/__init__.py memorytalk/repository/v4/schema.py \
        memorytalk/tests/repository/__init__.py memorytalk/tests/repository/v4/__init__.py \
        memorytalk/tests/repository/v4/conftest.py memorytalk/tests/repository/v4/schema/
git commit -m "feat(v4): SQLite DDL for the 5 card tables + repository test harness"
```

---

### Task 2: pos_ id helpers

**Files:**
- Modify: `memorytalk/util/ids.py`
- Create: `memorytalk/tests/util/v4_ids/{__init__.py, README.md, test.py}`

- [ ] **Step 1: Write the failing test**

`memorytalk/tests/util/v4_ids/test.py`:

```python
"""v4_ids — pos_ id mint + parse. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.util.ids import (
    POSITION_PREFIX, IdKind, InvalidIdError, new_position_id, parse_id,
)


def test_new_position_id_has_prefix():
    pid = new_position_id()
    assert pid.startswith(POSITION_PREFIX)
    assert len(pid) > len(POSITION_PREFIX)


def test_parse_position_id():
    kind, raw = parse_id("pos_01jzp3nq")
    assert kind is IdKind.POSITION
    assert raw == "01jzp3nq"


def test_parse_card_still_works():
    kind, _ = parse_id("card_01jz8k2m")
    assert kind is IdKind.CARD


def test_parse_unknown_prefix_raises():
    with pytest.raises(InvalidIdError):
        parse_id("nope_123")
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest memorytalk/tests/util/v4_ids/test.py -v`
Expected: FAIL with `ImportError: cannot import name 'POSITION_PREFIX'`.

- [ ] **Step 3: Implement in `memorytalk/util/ids.py`**

Add the constant near the other prefixes:

```python
POSITION_PREFIX = "pos_"
```

Add to the `IdKind` enum:

```python
    POSITION = "position"
```

Add the mint function (next to `new_card_id`):

```python
def new_position_id() -> str:
    return f"{POSITION_PREFIX}{ULID()}"
```

Add to the `parse_id` prefix tuple (before the `REVIEW_PREFIX` row):

```python
        (POSITION_PREFIX, IdKind.POSITION),
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest memorytalk/tests/util/v4_ids/test.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Write README**

`memorytalk/tests/util/v4_ids/README.md`:

```markdown
# v4_ids — pos_ 前缀 id

## 这个场景在测什么
v4 新增的 Position id(`pos_<ulid>`)能 mint、能被 `parse_id` 认成
`IdKind.POSITION`;card_ 等老前缀不受影响;未知前缀仍报 `InvalidIdError`。

## 不在这测什么
- card_ / sess- / review_ 的既有解析 → 既有 ids 测试
```

- [ ] **Step 6: Commit**

```bash
git add memorytalk/util/ids.py memorytalk/tests/util/v4_ids/
git commit -m "feat(v4): pos_ position id mint + parse"
```

---

### Task 3: v4 schemas (models)

**Files:**
- Create: `memorytalk/schemas/v4/__init__.py` (empty)
- Create: `memorytalk/schemas/v4/card.py`
- Create: `memorytalk/schemas/v4/requests.py`
- Create: `memorytalk/tests/schemas/__init__.py` (empty, if absent)
- Create: `memorytalk/tests/schemas/v4/{__init__.py, README.md, test.py}`

- [ ] **Step 1: Write the failing test**

`memorytalk/tests/schemas/v4/test.py`:

```python
"""v4 schemas — models + defaults. See README.md."""
from __future__ import annotations

from memorytalk.schemas.v4.card import Card, Position, CardLink, CardSession
from memorytalk.schemas.v4.requests import (
    CreateCardRequest, CreatePositionRequest, CreateReviewRequest, CreateLinkRequest,
)


def test_position_defaults():
    p = Position(position_id="pos_1", card_id="card_1", claim="x", created_at="t")
    assert p.up_count == 0 and p.down_count == 0 and p.neutral_count == 0
    assert p.review_count == 0
    assert p.scope == ""
    assert p.forked_from_position_id is None


def test_card_defaults():
    c = Card(card_id="card_1", issue="why?", created_at="t")
    assert c.position_count == 0 and c.link_count == 0
    assert c.positions == [] and c.links == [] and c.sessions == []


def test_card_link_carries_target_type():
    e = CardLink(card_id="card_1", type="specializes",
                 target_id="card_2", target_type="card", created_at="t")
    assert e.target_type == "card"


def test_create_card_request_optional_card_id():
    r = CreateCardRequest(issue="why?")
    assert r.card_id is None


def test_create_review_argument_literal():
    r = CreateReviewRequest(position_id="pos_1", session_id="sess-1",
                            indexes="1-3", argument=1)
    assert r.argument == 1
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest memorytalk/tests/schemas/v4/test.py -v`
Expected: FAIL with `ModuleNotFoundError: memorytalk.schemas.v4.card`.

- [ ] **Step 3: Implement `memorytalk/schemas/v4/card.py`**

```python
"""v4 read models: Card (≡Issue), Position, CardLink, CardSession.

Field names mirror docs/structure/v4/. credence is NOT a stored field —
the service computes it at read time and injects it into the response
DTOs (defined in the service plan), so it is absent here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Position(BaseModel):
    position_id: str
    card_id: str
    claim: str
    created_at: str
    up_count: int = 0
    down_count: int = 0
    neutral_count: int = 0
    review_count: int = 0
    scope: str = ""
    forked_from_position_id: str | None = None


class CardLink(BaseModel):
    card_id: str                       # subject (NOT from/to)
    type: Literal[
        "specializes", "suggested_by", "questions", "replaces", "related"
    ]
    target_id: str
    target_type: Literal["card", "position"]
    created_at: str


class CardSession(BaseModel):
    card_id: str
    session_id: str
    position_id: str = ""        # "" = card-level association
    indexes: str
    created_at: str


class Card(BaseModel):
    card_id: str
    issue: str
    created_at: str
    position_count: int = 0
    link_count: int = 0
    positions: list[Position] = Field(default_factory=list)
    links: list[CardLink] = Field(default_factory=list)
    sessions: list[CardSession] = Field(default_factory=list)
```

- [ ] **Step 4: Implement `memorytalk/schemas/v4/requests.py`**

```python
"""v4 write request/response models (API + service boundary)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SourceRef(BaseModel):
    session_id: str
    indexes: str


class CreateCardRequest(BaseModel):
    issue: str
    card_id: str | None = None


class CreateCardResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str


class CreatePositionRequest(BaseModel):
    claim: str
    scope: str = ""
    source: SourceRef | None = None
    forked_from_position_id: str | None = None
    position_id: str | None = None


class CreatePositionResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    position_id: str


class CreateReviewRequest(BaseModel):
    position_id: str
    session_id: str
    indexes: str
    argument: Literal[-1, 0, 1]
    comment: str | None = None
    review_id: str | None = None


class CreateReviewResponse(BaseModel):
    status: Literal["ok"] = "ok"
    review_id: str
    position_id: str
    argument: int


class CreateLinkRequest(BaseModel):
    card_id: str
    type: Literal[
        "specializes", "suggested_by", "questions", "replaces", "related"
    ]
    target_id: str


class CreateLinkResponse(BaseModel):
    status: Literal["ok"] = "ok"
    card_id: str
    type: str
    target_id: str
    target_type: str
```

- [ ] **Step 5: Run — verify pass + write README**

Run: `pytest memorytalk/tests/schemas/v4/test.py -v`
Expected: 5 PASS.

`memorytalk/tests/schemas/v4/README.md`:

```markdown
# v4 schemas — 模型 + 默认值

## 这个场景在测什么
Card / Position / CardLink / CardSession 读模型 + 4 个 create 请求模型的字段
默认值与类型约束:Position 计数默认 0、scope 默认空、无 credence 字段;
CardLink 带 target_type;CreateReview.argument 限定 {-1,0,1}。

## 不在这测什么
- 持久化 round-trip → tests/repository/v4/
- credence 现算 → service plan
```

- [ ] **Step 6: Commit**

```bash
git add memorytalk/schemas/v4/ memorytalk/tests/schemas/
git commit -m "feat(v4): Pydantic read + request/response models"
```

---

### Task 4: V4CardStore

**Files:**
- Create: `memorytalk/repository/v4/cards.py`
- Create: `memorytalk/tests/repository/v4/cards/{__init__.py, README.md, test.py}`

- [ ] **Step 1: Write the failing test**

`memorytalk/tests/repository/v4/cards/test.py`:

```python
"""cards — V4CardStore row + file round-trip, counter bumps, list. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.cards import V4CardStore


@pytest.fixture
def cards(v4db):
    return V4CardStore(v4db.conn, v4db.storage)


async def test_insert_then_get(cards):
    await cards.insert("card_01jz8k2m", "why?", "2026-06-01T00:00:00Z")
    row = await cards.get("card_01jz8k2m")
    assert row["issue"] == "why?"
    assert row["position_count"] == 0 and row["link_count"] == 0


async def test_write_doc_round_trip(cards):
    await cards.write_doc(
        {"card_id": "card_01jz8k2m", "issue": "why?", "created_at": "t"})
    doc = await cards.read_doc("card_01jz8k2m")
    assert doc["issue"] == "why?"


async def test_bump_position_count(cards):
    await cards.insert("card_01jz8k2m", "why?", "t")
    await cards.bump_position_count("card_01jz8k2m")
    await cards.bump_position_count("card_01jz8k2m")
    row = await cards.get("card_01jz8k2m")
    assert row["position_count"] == 2


async def test_bump_link_count(cards):
    await cards.insert("card_01jz8k2m", "why?", "t")
    await cards.bump_link_count("card_01jz8k2m")
    row = await cards.get("card_01jz8k2m")
    assert row["link_count"] == 1


async def test_exists_and_count(cards):
    assert await cards.exists("card_x") is False
    await cards.insert("card_x", "q", "t")
    assert await cards.exists("card_x") is True
    assert await cards.count() == 1


async def test_list_orders_by_created_desc(cards):
    await cards.insert("card_a", "qa", "2026-06-01T00:00:00Z")
    await cards.insert("card_b", "qb", "2026-06-02T00:00:00Z")
    total, rows = await cards.list_cards(limit=10)
    assert total == 2
    assert rows[0]["card_id"] == "card_b"  # newest first
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest memorytalk/tests/repository/v4/cards/test.py -v`
Expected: FAIL with `ModuleNotFoundError: memorytalk.repository.v4.cards`.

- [ ] **Step 3: Implement `memorytalk/repository/v4/cards.py`**

```python
"""V4CardStore — card (≡Issue) persistence: file canonical + SQLite index.

File layout::

    cards/<bucket>/<card_id>/card.json              (canonical: issue + created_at)
    cards/<bucket>/<card_id>/positions/<pid>.json   (written by PositionStore)

SQLite ``cards`` row mirrors issue + created_at and holds the redundant
position_count / link_count counters.
"""
from __future__ import annotations

import json

import aiosqlite

from memorytalk.provider.storage import Storage


class V4CardStore:
    PREFIX = "cards"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/card.json"

    # ── file layer ──
    async def write_doc(self, card: dict) -> None:
        await self.storage.write_text(
            self._doc_key(card["card_id"]),
            json.dumps(card, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(card_id))
        return json.loads(text) if text else None

    # ── cards table ──
    async def insert(self, card_id: str, issue: str, created_at: str) -> None:
        await self.conn.execute(
            "INSERT INTO cards (card_id, issue, created_at, position_count, link_count) "
            "VALUES (?, ?, ?, 0, 0)",
            (card_id, issue, created_at),
        )
        await self.conn.commit()

    async def get(self, card_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT card_id, issue, created_at, position_count, link_count "
            "FROM cards WHERE card_id = ?", (card_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {
            "card_id": row["card_id"], "issue": row["issue"],
            "created_at": row["created_at"],
            "position_count": row["position_count"], "link_count": row["link_count"],
        }

    async def exists(self, card_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM cards WHERE card_id = ?", (card_id,),
        ) as cur:
            return await cur.fetchone() is not None

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM cards") as cur:
            return (await cur.fetchone())[0]

    async def bump_position_count(self, card_id: str, delta: int = 1) -> None:
        await self.conn.execute(
            "UPDATE cards SET position_count = position_count + ? WHERE card_id = ?",
            (delta, card_id),
        )
        await self.conn.commit()

    async def bump_link_count(self, card_id: str, delta: int = 1) -> None:
        await self.conn.execute(
            "UPDATE cards SET link_count = link_count + ? WHERE card_id = ?",
            (delta, card_id),
        )
        await self.conn.commit()

    async def list_cards(
        self, *, since: str | None = None, until: str | None = None, limit: int = 20,
    ) -> tuple[int, list[dict]]:
        clauses: list[str] = []
        params: list = []
        if since:
            clauses.append("created_at >= ?"); params.append(since)
        if until:
            clauses.append("created_at <= ?"); params.append(until)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        async with self.conn.execute(
            f"SELECT COUNT(*) FROM cards {where}", params,
        ) as cur:
            total = (await cur.fetchone())[0]
        async with self.conn.execute(
            f"SELECT card_id, issue, created_at, position_count, link_count "
            f"FROM cards {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ) as cur:
            rows = await cur.fetchall()
        return total, [dict(r) for r in rows]
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest memorytalk/tests/repository/v4/cards/test.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Write README**

`memorytalk/tests/repository/v4/cards/README.md`:

```markdown
# cards — V4CardStore

## 这个场景在测什么
卡的 SQLite 行 + card.json 文件 round-trip;position_count / link_count
两个冗余计数能 +1;exists / count;list_cards 按 created_at 倒序 + total。

## 不在这测什么
- Position / review / link / session → 各自场景
- 多表原子 create 编排 → service plan

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn` / `.storage`;场景内一个小 fixture 自建本 store
```

- [ ] **Step 6: Commit**

```bash
git add memorytalk/repository/v4/cards.py memorytalk/tests/repository/v4/cards/
git commit -m "feat(v4): V4CardStore (row + card.json + position/link counters)"
```

---

### Task 5: PositionStore

**Files:**
- Create: `memorytalk/repository/v4/positions.py`
- Create: `memorytalk/tests/repository/v4/positions/{__init__.py, README.md, test.py}`

- [ ] **Step 1: Write the failing test**

`memorytalk/tests/repository/v4/positions/test.py`:

```python
"""positions — PositionStore row + file, argument bump, list_for_card. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.positions import PositionStore


@pytest.fixture
def positions(v4db):
    return PositionStore(v4db.conn, v4db.storage)


async def test_insert_then_get(positions):
    await positions.insert(
        "pos_1", "card_1", "be concise", "t", scope="daily", forked_from_position_id=None)
    row = await positions.get("pos_1")
    assert row["claim"] == "be concise"
    assert row["scope"] == "daily"
    assert row["up_count"] == 0 and row["review_count"] == 0


async def test_write_doc_round_trip(positions):
    await positions.write_doc(
        "card_1", {"position_id": "pos_1", "claim": "x", "created_at": "t"})
    doc = await positions.read_doc("card_1", "pos_1")
    assert doc["claim"] == "x"


async def test_bump_argument_up(positions):
    await positions.insert("pos_1", "card_1", "x", "t")
    await positions.bump_argument("pos_1", 1)
    await positions.bump_argument("pos_1", 1)
    await positions.bump_argument("pos_1", -1)
    await positions.bump_argument("pos_1", 0)
    row = await positions.get("pos_1")
    assert row["up_count"] == 2 and row["down_count"] == 1 and row["neutral_count"] == 1
    assert row["review_count"] == 4  # total = up+down+neutral


async def test_bump_argument_rejects_bad_value(positions):
    await positions.insert("pos_1", "card_1", "x", "t")
    with pytest.raises(ValueError):
        await positions.bump_argument("pos_1", 2)


async def test_list_for_card(positions):
    await positions.insert("pos_a", "card_1", "a", "t")
    await positions.insert("pos_b", "card_1", "b", "t")
    await positions.insert("pos_c", "card_2", "c", "t")
    rows = await positions.list_for_card("card_1")
    assert {r["position_id"] for r in rows} == {"pos_a", "pos_b"}
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest memorytalk/tests/repository/v4/positions/test.py -v`
Expected: FAIL with `ModuleNotFoundError: memorytalk.repository.v4.positions`.

- [ ] **Step 3: Implement `memorytalk/repository/v4/positions.py`**

```python
"""PositionStore — answer candidate persistence: file canonical + SQLite.

File: cards/<bucket>/<card_id>/positions/<position_id>.json
(canonical immutable core: claim + created_at only; scope and
forked_from_position_id are mutable runtime state in SQLite, not part
of the write-once file). SQLite mirrors claim + created_at plus the
up/down/neutral/review counters + scope + forked_from_position_id.
credence is NOT stored -- computed by the service. No FOREIGN KEY.
"""
from __future__ import annotations

import json

import aiosqlite

from memorytalk.provider.storage import Storage


class PositionStore:
    PREFIX = "cards"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str, position_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/positions/{position_id}.json"

    # ── file layer ──
    async def write_doc(self, card_id: str, position: dict) -> None:
        await self.storage.write_text(
            self._doc_key(card_id, position["position_id"]),
            json.dumps(position, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str, position_id: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(card_id, position_id))
        return json.loads(text) if text else None

    # ── positions table ──
    async def insert(
        self, position_id: str, card_id: str, claim: str, created_at: str,
        *, scope: str = "", forked_from_position_id: str | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO positions "
            "(position_id, card_id, claim, created_at, up_count, down_count, "
            " neutral_count, review_count, scope, forked_from_position_id) "
            "VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?)",
            (position_id, card_id, claim, created_at, scope, forked_from_position_id),
        )
        await self.conn.commit()

    async def get(self, position_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM positions WHERE position_id = ?", (position_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def exists(self, position_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM positions WHERE position_id = ?", (position_id,),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_for_card(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM positions WHERE card_id = ? ORDER BY created_at ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def bump_argument(self, position_id: str, argument: int) -> None:
        """Increment the argument-specific bucket + review_count."""
        col = {1: "up_count", -1: "down_count", 0: "neutral_count"}.get(argument)
        if col is None:
            raise ValueError(f"argument must be -1/0/1, got {argument!r}")
        await self.conn.execute(
            f"UPDATE positions SET {col} = {col} + 1, review_count = review_count + 1 "
            f"WHERE position_id = ?",
            (position_id,),
        )
        await self.conn.commit()
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest memorytalk/tests/repository/v4/positions/test.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Write README**

`memorytalk/tests/repository/v4/positions/README.md`:

```markdown
# positions — PositionStore

## 这个场景在测什么
答案的 SQLite 行 + positions/<pid>.json round-trip;`bump_argument` 按
+1/-1/0 各自加 up/down/neutral_count 且 review_count = 三者之和;非法
argument 报 ValueError;list_for_card 只返回该卡的答案。

## 不在这测什么
- credence 现算排序 → service plan
- review 行本身 → reviews 场景

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn` / `.storage`;场景内一个小 fixture 自建本 store
```

- [ ] **Step 6: Commit**

```bash
git add memorytalk/repository/v4/positions.py memorytalk/tests/repository/v4/positions/
git commit -m "feat(v4): PositionStore (row + json + argument counters)"
```

---

### Task 6: V4ReviewStore

**Files:**
- Create: `memorytalk/repository/v4/reviews.py`
- Create: `memorytalk/tests/repository/v4/reviews/{__init__.py, README.md, test.py}`

- [ ] **Step 1: Write the failing test**

`memorytalk/tests/repository/v4/reviews/test.py`:

```python
"""reviews — V4ReviewStore insert / list_for_position / count. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.reviews import V4ReviewStore


@pytest.fixture
def reviews(v4db):
    return V4ReviewStore(v4db.conn)


async def test_insert_then_list(reviews):
    # insert args: review_id, position_id, card_id, session_id, indexes, argument, comment, created_at
    await reviews.insert(
        "review_1", "pos_1", "card_1", "sess-a", "1-3", 1, "validated", "2026-06-01T00:00:00Z")
    await reviews.insert(
        "review_2", "pos_1", "card_1", "sess-b", "4-5", -1, None, "2026-06-02T00:00:00Z")
    rows = await reviews.list_for_position("pos_1")
    assert [r["review_id"] for r in rows] == ["review_2", "review_1"]  # newest first
    assert rows[0]["argument"] == -1
    assert rows[0]["card_id"] == "card_1"


async def test_list_scoped_to_position(reviews):
    await reviews.insert("review_1", "pos_1", "card_1", "sess-a", "1", 1, None, "t")
    await reviews.insert("review_2", "pos_2", "card_1", "sess-a", "1", 1, None, "t")
    assert len(await reviews.list_for_position("pos_1")) == 1


async def test_exists_and_count(reviews):
    assert await reviews.exists("review_1") is False
    await reviews.insert("review_1", "pos_1", "card_1", "sess-a", "1", 0, None, "t")
    assert await reviews.exists("review_1") is True
    assert await reviews.count() == 1
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest memorytalk/tests/repository/v4/reviews/test.py -v`
Expected: FAIL with `ModuleNotFoundError: memorytalk.repository.v4.reviews`.

- [ ] **Step 3: Implement `memorytalk/repository/v4/reviews.py`**

```python
"""V4ReviewStore — stances on a Position (argument in {-1,0,1}).

SQLite-only here; the file mirror (reviews appended under the card dir)
is wired in the service plan alongside the旁白/annotation write path.
No FOREIGN KEY on position_id.
"""
from __future__ import annotations

import aiosqlite


class V4ReviewStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, review_id: str, position_id: str, card_id: str, session_id: str,
        indexes: str, argument: int, comment: str | None, created_at: str,
    ) -> None:
        # card_id is the redundant cache (= positions.card_id); the service
        # backfills it from position_id before calling.
        await self.conn.execute(
            "INSERT INTO reviews "
            "(review_id, position_id, card_id, session_id, indexes, argument, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (review_id, position_id, card_id, session_id, indexes, argument, comment, created_at),
        )
        await self.conn.commit()

    async def exists(self, review_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM reviews WHERE review_id = ?", (review_id,),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_for_position(self, position_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM reviews WHERE position_id = ? ORDER BY created_at DESC",
            (position_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM reviews") as cur:
            return (await cur.fetchone())[0]
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest memorytalk/tests/repository/v4/reviews/test.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Write README**

`memorytalk/tests/repository/v4/reviews/README.md`:

```markdown
# reviews — V4ReviewStore

## 这个场景在测什么
对 Position 表态的 review 行 insert;list_for_position 按 created_at 倒序
且只返回该 position;exists / count。

## 不在这测什么
- bump 到 position 计数(那是 PositionStore.bump_argument)→ service 编排时串起来
- review 文件镜像 → service plan

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn` / `.storage`;场景内一个小 fixture 自建本 store
```

- [ ] **Step 6: Commit**

```bash
git add memorytalk/repository/v4/reviews.py memorytalk/tests/repository/v4/reviews/
git commit -m "feat(v4): V4ReviewStore (stances on a Position)"
```

---

### Task 7: CardLinkStore

**Files:**
- Create: `memorytalk/repository/v4/links.py`
- Create: `memorytalk/tests/repository/v4/links/{__init__.py, README.md, test.py}`

- [ ] **Step 1: Write the failing test**

`memorytalk/tests/repository/v4/links/test.py`:

```python
"""links — CardLinkStore: target_type derive, idempotent, out/in. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.links import CardLinkStore


@pytest.fixture
def links(v4db):
    return CardLinkStore(v4db.conn)


async def test_insert_derives_target_type_card(links):
    await links.insert("card_1", "specializes", "card_2", "t")
    out = await links.list_out("card_1")
    assert out[0]["target_type"] == "card"


async def test_insert_derives_target_type_position(links):
    await links.insert("card_1", "suggested_by", "pos_9", "t")
    out = await links.list_out("card_1")
    assert out[0]["target_type"] == "position"


async def test_insert_is_idempotent(links):
    await links.insert("card_1", "specializes", "card_2", "t")
    await links.insert("card_1", "specializes", "card_2", "t2")  # same edge
    assert len(await links.list_out("card_1")) == 1


async def test_list_in_reverse(links):
    await links.insert("card_1", "replaces", "card_2", "t")
    incoming = await links.list_in("card_2")
    assert incoming[0]["card_id"] == "card_1"
    assert incoming[0]["type"] == "replaces"
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest memorytalk/tests/repository/v4/links/test.py -v`
Expected: FAIL with `ModuleNotFoundError: memorytalk.repository.v4.links`.

- [ ] **Step 3: Implement `memorytalk/repository/v4/links.py`**

```python
"""CardLinkStore — card↔card IBIS edges (card_links).

A row = subject ``card_id`` + ``type`` + ``target_id`` (NOT symmetric
from/to). ``target_type`` ('card' | 'position') is derived from the
target_id prefix and stored for filtering. Idempotent on the PK
(card_id, type, target_id). No FOREIGN KEY — targets may dangle.
"""
from __future__ import annotations

import aiosqlite


def _target_type(target_id: str) -> str:
    if target_id.startswith("pos_"):
        return "position"
    return "card"


class CardLinkStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, type_: str, target_id: str, created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO card_links "
            "(card_id, type, target_id, target_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (card_id, type_, target_id, _target_type(target_id), created_at),
        )
        await self.conn.commit()

    async def list_out(self, card_id: str) -> list[dict]:
        """Edges where this card is the subject."""
        async with self.conn.execute(
            "SELECT * FROM card_links WHERE card_id = ? ORDER BY created_at ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_in(self, target_id: str) -> list[dict]:
        """Edges pointing at this id (reverse lookup, idx_v4_links_target)."""
        async with self.conn.execute(
            "SELECT * FROM card_links WHERE target_id = ? ORDER BY created_at ASC",
            (target_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
```

> `INSERT OR IGNORE` gives the documented idempotency on the `(card_id, type, target_id)` PK. `related` normalization (sorting endpoints so A→B == B→A) is a service-layer concern (next plans) — not enforced here.

- [ ] **Step 4: Run — verify pass**

Run: `pytest memorytalk/tests/repository/v4/links/test.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Write README**

`memorytalk/tests/repository/v4/links/README.md`:

```markdown
# links — CardLinkStore

## 这个场景在测什么
建一条 card↔card 边:`target_type` 从 target_id 前缀自动派生(card_ →
card,pos_ → position);同 `(card_id, type, target_id)` 重复插入幂等
(INSERT OR IGNORE);list_out 取本卡为主体的边,list_in 反查指向某 id 的边。

## 不在这测什么
- related 无向规范化排序 → service plan
- 五类型白名单校验 → service / API plan(store 不校验类型)

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn` / `.storage`;场景内一个小 fixture 自建本 store
```

- [ ] **Step 6: Commit**

```bash
git add memorytalk/repository/v4/links.py memorytalk/tests/repository/v4/links/
git commit -m "feat(v4): CardLinkStore (IBIS edges + target_type derive + idempotent)"
```

---

### Task 8: CardSessionStore

**Files:**
- Create: `memorytalk/repository/v4/sessions.py`
- Create: `memorytalk/tests/repository/v4/sessions/{__init__.py, README.md, test.py}`

- [ ] **Step 1: Write the failing test**

`memorytalk/tests/repository/v4/sessions/test.py`:

```python
"""sessions — CardSessionStore provenance + reverse lookup. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.repository.v4.sessions import CardSessionStore


@pytest.fixture
def sessions(v4db):
    return CardSessionStore(v4db.conn)


async def test_insert_then_list_for_card(sessions):
    # insert args: card_id, session_id, position_id, indexes, created_at
    await sessions.insert("card_1", "sess-a", "pos_1", "11-15", "t")
    rows = await sessions.list_for_card("card_1")
    assert rows[0]["session_id"] == "sess-a"
    assert rows[0]["position_id"] == "pos_1"
    assert rows[0]["indexes"] == "11-15"


async def test_multi_session_per_card(sessions):
    await sessions.insert("card_1", "sess-a", "", "1-3", "t")   # "" = card-level
    await sessions.insert("card_1", "sess-b", "", "4-5", "t")
    assert len(await sessions.list_for_card("card_1")) == 2


async def test_same_card_session_different_position(sessions):
    # PK includes position_id → same card+session, two positions = 2 rows
    await sessions.insert("card_1", "sess-a", "pos_1", "1-3", "t")
    await sessions.insert("card_1", "sess-a", "pos_2", "4-5", "t")
    assert len(await sessions.list_for_card("card_1")) == 2


async def test_reverse_list_cards_for_session(sessions):
    await sessions.insert("card_1", "sess-a", "", "1-3", "t")
    await sessions.insert("card_2", "sess-a", "", "7-9", "t")
    cards = await sessions.list_cards_for_session("sess-a")
    assert {c["card_id"] for c in cards} == {"card_1", "card_2"}


async def test_insert_idempotent_on_pk(sessions):
    await sessions.insert("card_1", "sess-a", "", "1-3", "t")
    await sessions.insert("card_1", "sess-a", "", "1-3", "t2")  # same (card,session,position)
    assert len(await sessions.list_for_card("card_1")) == 1
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest memorytalk/tests/repository/v4/sessions/test.py -v`
Expected: FAIL with `ModuleNotFoundError: memorytalk.repository.v4.sessions`.

- [ ] **Step 3: Implement `memorytalk/repository/v4/sessions.py`**

```python
"""CardSessionStore — card↔session provenance (card_sessions).

Records where a card / position came from. Multi-session per card. No own
id; composite PK (card_id, session_id, indexes), idempotent re-insert. No
FOREIGN KEY. The canonical of this relation is the per-round旁白 annotation
(questions[]); this table is its derived index (see session-annotation.md).
"""
from __future__ import annotations

import aiosqlite


class CardSessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, session_id: str, position_id: str,
        indexes: str, created_at: str,
    ) -> None:
        # position_id "" = card-level association. PK is
        # (card_id, session_id, position_id); INSERT OR IGNORE makes re-insert
        # of the same triple idempotent.
        await self.conn.execute(
            "INSERT OR IGNORE INTO card_sessions "
            "(card_id, session_id, position_id, indexes, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (card_id, session_id, position_id, indexes, created_at),
        )
        await self.conn.commit()

    async def list_for_card(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM card_sessions WHERE card_id = ? ORDER BY created_at ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_cards_for_session(self, session_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM card_sessions WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest memorytalk/tests/repository/v4/sessions/test.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Write README**

`memorytalk/tests/repository/v4/sessions/README.md`:

```markdown
# sessions — CardSessionStore

## 这个场景在测什么
card↔session 出处:insert + list_for_card(带 position_id / indexes);
一卡多 session;同一卡+session 下不同 position 是两行(PK 含 position_id);
反查 list_cards_for_session(session → 哪些卡);同
(card_id, session_id, position_id) 重复插入幂等。

## 不在这测什么
- 旁白 annotation 写路径 / questions[] 解析 → service plan
- canonical pass 文件 → service plan

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn` / `.storage`;场景内一个小 fixture 自建本 store
```

- [ ] **Step 6: Commit**

```bash
git add memorytalk/repository/v4/sessions.py memorytalk/tests/repository/v4/sessions/
git commit -m "feat(v4): CardSessionStore (card↔session provenance + reverse lookup)"
```

---

### Task 9: Full-suite green + schema test re-verify

**Files:** none (verification only)

- [ ] **Step 1: Run the whole v4 repository suite**

Run: `pytest memorytalk/tests/repository/v4/ memorytalk/tests/util/v4_ids/ memorytalk/tests/schemas/v4/ -v`
Expected: all PASS (schema/test.py now resolves all five store imports from conftest).

- [ ] **Step 2: Run the full project suite to confirm no regressions**

Run: `pytest memorytalk/tests/ -q`
Expected: existing v3 tests still PASS; new v4 tests included.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A && git commit -m "test(v4): data-foundation suite green"
```

---

## Self-Review

**1. Spec coverage (against `docs/structure/v4/`):**
- `cards` table (issue + created_at + position_count + link_count) → Task 1 DDL, Task 4 store ✓
- `positions` table (claim + up/down/neutral/review_count + scope + forked_from, no credence) → Task 1 DDL, Task 5 store ✓
- `reviews` table (position_id + argument ±1/0 + indexes + comment) → Task 1, Task 6 ✓
- `card_links` (card_id subject + type + target_id + target_type, idempotent PK, no from/to) → Task 1, Task 7 ✓
- `card_sessions` (card_id + session_id + position_id + indexes, multi-session, reverse lookup) → Task 1, Task 8 ✓
- No FOREIGN KEY anywhere → DDL has none ✓
- credence never stored → asserted absent in Task 1 schema test ✓
- pos_ id prefix → Task 2 ✓
- Pydantic models (Card/Position/CardLink/CardSession + requests) → Task 3 ✓
- File-canonical card.json / positions/<pid>.json → Task 4 / Task 5 ✓
- Scenario test layout (README + __init__ + test, shared conftest) like searchbase → all test tasks ✓
- **Deferred (correctly out of scope for the data layer):** credence computation, related-edge normalization, IBIS type whitelist validation, source/index range validation, review file-mirror, embedding/searchbase, migration wiring → Plans 2–4 (noted at each store).

**2. Placeholder scan:** No TBD/TODO; every code step has complete code; every run step has an exact command + expected result.

**3. Type consistency:** Store ctor signatures match how each scenario's fixture builds them: `V4CardStore` / `PositionStore` take `(conn, storage)`; `V4ReviewStore` / `CardLinkStore` / `CardSessionStore` take `(conn)`. Method names used in tests match the implementations (`bump_position_count`, `bump_link_count`, `bump_argument`, `list_for_card`, `list_out`, `list_in`, `list_cards_for_session`, `list_cards`). `argument` (v4) used throughout, not `score` (v3). `target_type` derived consistently in Task 7. Scenarios are decoupled: each test file imports only its own store, so every store task is independently green.

**Facts verified against the codebase (not assumed):**
- `memorytalk/provider/storage.py` exports `Storage` (Protocol) + `LocalStorage` (concrete) with `write_text` / `read_text` / `append_text` / `delete_prefix` / `list_subkeys`.
- `SQLiteStore.open_connection` sets `conn.row_factory = aiosqlite.Row` and `PRAGMA foreign_keys = ON` (v4 declares no FK clauses, so the pragma is a no-op for these tables).
- Top-level `memorytalk/tests/conftest.py` provides `data_root`; `asyncio_mode=auto` so plain `async def test_*` run without a marker.
