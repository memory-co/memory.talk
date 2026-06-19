# v3 card → insight Rename + v4 Tables Implementation Plan (Plan 2 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the entire v3 "card" subsystem to "insight" (SQLite tables, LanceDB collection, file dir, classes, routes, CLI, schemas), drop the unused `reviews` feature, and create the v4 card tables — freeing the `card`/`cards`/`reviews` names for v4.

**Architecture:** All schema/data **transform logic lives in `migrations/`** (migration `v3` = rename + drop reviews; migration `v4` = create v4 tables). The application code is adapted in the same plan so the suite stays green. v3 keeps its `card_<ulid>` ids (two-stage: routing is namespaced `/v3` vs `/v4`, so the shared `card_` prefix is unambiguous). The LanceDB collection move is a cheap directory/table rename (new `rename_collection` admin primitive), not a re-embed.

**Tech Stack:** Python 3.11, Pydantic v2, `aiosqlite`, `lancedb` (async), Click, pytest (`asyncio_mode=auto`; migration tests use explicit `@pytest.mark.asyncio` to match the existing `tests/migration/` style).

## Global Constraints

- **All migration transform logic stays in `migrations/vN/`** — no schema/data transforms in `service/` or app-startup hooks. (Adding a reusable `rename_collection` primitive to the searchbase admin API is allowed framework support; business services still never touch admin.)
- **No FOREIGN KEY** in any new/changed SQLite DDL (repo hard rule). The v3 legacy tables keep their existing FKs; renames let SQLite auto-rewrite FK refs.
- **Keep `card_<ulid>` ids** — do NOT rewrite id prefixes. `util/ids.py` `CARD_PREFIX`/`IdKind.CARD` stay.
- **Frozen migrations:** do NOT edit `migrations/v1/*` or `migrations/v2/*` DDL bodies (they are historical snapshots). New work goes in `migrations/v3/` and `migrations/v4/`. (Exception: v1/v2 `run()` signatures gain a `data_root=None` kwarg in Task 2 — additive, ignored.)
- **Pydantic, not dataclass**, for all value types. Scenario tests follow the `tests/<area>/<scenario>/{README.md, __init__.py, test.py}` layout; migration tests live under `tests/migration/<scenario>/`.
- Design source of truth: `docs/works/v4/insight-migration.md`, `docs/works/v3/migration.md`.

---

## Exhaustive File Map (from code-surface audit)

**Create:**
- `memorytalk/migrations/v3/__init__.py`, `init_database.py`, `up_database.py`, `init_searchbase.py`, `up_searchbase.py`
- `memorytalk/migrations/v4/__init__.py`, `init_database.py`, `up_database.py`, `init_searchbase.py`, `up_searchbase.py`
- `memorytalk/repository/insights.py` (from `cards.py`), `memorytalk/service/insights.py` (from `service/cards.py`), `memorytalk/api/insights.py` (from `api/cards.py`), `memorytalk/cli/insight.py` (from `cli/card.py`), `memorytalk/schemas/insight.py` (from `schemas/card.py`), `memorytalk/schemas/insights.py` (from `schemas/cards.py`)
- Migration test scenario dirs under `memorytalk/tests/migration/v3_insight_rename/` and `v4_card_tables/`

**Modify (framework + wiring):**
- `memorytalk/searchbase/_types.py` (+`rename_collection`), `memorytalk/searchbase/local/_admin.py` (impl)
- `memorytalk/migration/runner.py` (pass `data_root` to `run()`)
- `memorytalk/migrations/v1/{up,init}_{database,searchbase}.py` + `v2/*` `run()` signatures (+`data_root=None`)
- `memorytalk/service/searchbase_schema.py` (`CARDS`→`INSIGHTS="insights"`)
- `memorytalk/repository/store.py`, `memorytalk/service/__init__.py`, `memorytalk/schemas/__init__.py`, `memorytalk/api/__init__.py`, `memorytalk/cli/__init__.py`
- `memorytalk/service/read.py`, `recall.py`, `search.py`; `memorytalk/api/read.py`; `memorytalk/cli/_format.py`

**Delete (review retirement):**
- `memorytalk/service/reviews.py`, `memorytalk/repository/reviews.py`, `memorytalk/api/reviews.py`, `memorytalk/cli/review.py`, `memorytalk/schemas/review.py`, `memorytalk/schemas/reviews.py`, `memorytalk/tests/api/test_reviews.py`

**Rename (tests):** `tests/api/test_cards*.py`→`test_insights*.py`, `tests/cli/test_card*`→`test_insight*` (exact set verified during Task 12).

---

## Phase A — Framework extensions

### Task 1: `rename_collection` admin primitive

**Files:**
- Modify: `memorytalk/searchbase/_types.py` (AdminBackend Protocol, after `drop_collection` ~line 101)
- Modify: `memorytalk/searchbase/local/_admin.py` (after `drop_collection` ~line 138)
- Test: `memorytalk/tests/searchbase/local/rename_collection/{README.md,__init__.py,test.py}`

**Interfaces — Produces:** `AdminBackend.rename_collection(old: str, new: str) -> None` (idempotent: no-op if `old` absent or `new` already exists).

- [ ] **Step 1: Write the failing test** `memorytalk/tests/searchbase/local/rename_collection/test.py`

```python
"""rename_collection — collection rename keeps rows, frees old name. See README.md."""
from __future__ import annotations

import pytest


async def test_rename_moves_collection(local_backend):
    # local_backend: a LocalSearchBackend fixture with collections {"cards","rounds"} (see conftest)
    admin = local_backend.admin()
    await admin.create_collection("cards", {"fields": {}})
    await local_backend.upsert("cards", [{"id": "card_1", "text": "hello"}])
    await admin.rename_collection("cards", "insights")
    cols = await admin.list_collections()
    assert "insights" in cols and "cards" not in cols
    assert await local_backend.count("insights") == 1


async def test_rename_idempotent_when_old_absent(local_backend):
    admin = local_backend.admin()
    await admin.rename_collection("nonexistent", "whatever")  # no error
```

> Check `memorytalk/tests/searchbase/local/conftest.py` for the existing backend fixture name/shape; reuse it (the searchbase scenario tests already build a `LocalSearchBackend`). Adjust the fixture name in the test to match.

- [ ] **Step 2: Run — expect FAIL** `pytest memorytalk/tests/searchbase/local/rename_collection/test.py -v` → `AttributeError: 'LocalAdminBackend' object has no attribute 'rename_collection'`.

- [ ] **Step 3: Add to the Protocol** in `memorytalk/searchbase/_types.py` after `drop_collection`:
```python
    async def rename_collection(self, old: str, new: str) -> None:
        """Rename a collection (data preserved). Idempotent: no-op if
        ``old`` is absent or ``new`` already exists."""
        ...
```

- [ ] **Step 4: Implement in `LocalAdminBackend`** (`memorytalk/searchbase/local/_admin.py`):
```python
    async def rename_collection(self, old: str, new: str) -> None:
        tables = await self._index.db.list_tables()
        if old not in tables or new in tables:
            return
        try:
            await self._index.db.rename_table(old, new)
        except (AttributeError, NotImplementedError):
            # lancedb build without rename_table: rename the .lance dir,
            # then reconnect so the handle sees the new table.
            import os
            await self._index.db.close()
            os.rename(
                self._index.data_dir / f"{old}.lance",
                self._index.data_dir / f"{new}.lance",
            )
            import lancedb
            self._index.db = await lancedb.connect_async(str(self._index.data_dir))
        # internal bookkeeping (mirror create/drop_collection's updates)
        self._index._declared.pop(old, None)
```

> Verify against `_admin.py`/`index.py`: confirm `self._index.db`, `self._index.data_dir`, and the internal tracking set names (`_declared` / `_collections` / `_auto_split`). Mirror exactly what `create_collection`/`drop_collection` touch so the in-memory view stays consistent. If `db.rename_table` exists in the installed lancedb, the fallback never runs.

- [ ] **Step 5: Run — expect PASS** `pytest memorytalk/tests/searchbase/local/rename_collection/test.py -v` (2 passed).

- [ ] **Step 6: README + commit** (`tests/.../rename_collection/README.md`: 测什么 = collection 改名保留行、幂等; 不测 = 跨进程/远端). 
```bash
git add memorytalk/searchbase/_types.py memorytalk/searchbase/local/_admin.py memorytalk/tests/searchbase/local/rename_collection/
git commit -m "feat(searchbase): rename_collection admin primitive (dir/table rename, no re-embed)"
```

### Task 2: Migration runner passes `data_root` to `run()`

**Files:**
- Modify: `memorytalk/migration/runner.py` (`_run_method` ~line 178)
- Modify: `migrations/v1/{init,up}_{database,searchbase}.py`, `migrations/v2/{init,up}_{database,searchbase}.py` (8 `run` signatures)
- Test: `memorytalk/tests/migration/runner_data_root/{README.md,__init__.py,test.py}`

**Interfaces — Produces:** every migration `run(handle, *, data_root: Path | None = None)`. The runner passes the real `data_root`.

- [ ] **Step 1: Failing test** `memorytalk/tests/migration/runner_data_root/test.py`:
```python
"""runner_data_root — runner passes data_root kwarg to migration run(). See README.md."""
from __future__ import annotations

import pytest

from memorytalk.migrations.v2 import up_database as v2_up


@pytest.mark.asyncio
async def test_v2_up_accepts_data_root_kwarg():
    import aiosqlite
    from memorytalk.migrations.v1 import init_database as v1_init
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)      # must accept the kwarg now
    await v2_up.run(conn, data_root=None)
    await conn.close()
```

- [ ] **Step 2: Run — expect FAIL** (`run() got an unexpected keyword argument 'data_root'`).

- [ ] **Step 3: Update the 8 existing `run` signatures** in `migrations/v1/*` and `migrations/v2/*` from `async def run(conn):` / `async def run(admin):` to accept and ignore the kwarg:
```python
async def run(conn, *, data_root=None) -> None:   # data_root unused in v1/v2
```
(searchbase ones: `async def run(admin, *, data_root=None)`).

- [ ] **Step 4: Update the runner** `memorytalk/migration/runner.py` `_run_method`, change the call (~line 178):
```python
        await module.run(handle, data_root=self._data_root)
```

- [ ] **Step 5: Run — expect PASS**; also run the existing migration suite `pytest memorytalk/tests/migration -q` (no regressions).

- [ ] **Step 6: README + commit**
```bash
git add memorytalk/migration/runner.py memorytalk/migrations/v1 memorytalk/migrations/v2 memorytalk/tests/migration/runner_data_root/
git commit -m "feat(migration): pass data_root kwarg to migration run() (enables file-layer migrations)"
```

---

## Phase B — Migration v3 (rename storage + drop reviews)

### Task 3: `migrations/v3` database + files

**Files:**
- Create: `memorytalk/migrations/v3/__init__.py` (empty), `init_database.py`, `up_database.py`
- Test: `memorytalk/tests/migration/v3_insight_rename/{README.md,__init__.py,test.py}`

**Interfaces — Consumes:** `data_root` kwarg (Task 2). **Produces:** post-v3 SQLite has `insights`/`insight_stats`/`insight_source_cards` (no `cards`/`card_stats`/`card_source_cards`/`reviews`); file dir `cards/`→`insights/`.

- [ ] **Step 1: Write `migrations/v3/up_database.py`** (the v2→v3 delta — full code):
```python
"""v3 upgrade: rename card subsystem → insight + drop unused reviews.

Renames the 3 card tables, drops the (unused) reviews table + its indexes,
and moves the file-canonical dir cards/ → insights/. All transform logic
lives here (migrations/), per the migration design.
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite


async def _tables(conn) -> set[str]:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


async def run(conn: aiosqlite.Connection, *, data_root: Path | None = None) -> None:
    """v2 → v3. Idempotent."""
    names = await _tables(conn)
    # 1. Drop unused reviews (frees the name for v4) + its indexes.
    await conn.execute("DROP INDEX IF EXISTS idx_reviews_card")
    await conn.execute("DROP INDEX IF EXISTS idx_reviews_session")
    await conn.execute("DROP INDEX IF EXISTS idx_reviews_explore")
    await conn.execute("DROP TABLE IF EXISTS reviews")
    # 2. Rename the 3 card tables → insight* (only if not already done).
    if "cards" in names and "insights" not in names:
        await conn.execute("ALTER TABLE cards RENAME TO insights")
    if "card_stats" in names and "insight_stats" not in names:
        await conn.execute("ALTER TABLE card_stats RENAME TO insight_stats")
    if "card_source_cards" in names and "insight_source_cards" not in names:
        await conn.execute("ALTER TABLE card_source_cards RENAME TO insight_source_cards")
    # 3. Rename indexes for clarity (drop old names, recreate on new tables).
    await conn.execute("DROP INDEX IF EXISTS idx_cards_created")
    await conn.execute("DROP INDEX IF EXISTS idx_csc_source")
    await conn.execute("DROP INDEX IF EXISTS idx_cards_explore")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at)")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_insight_source ON insight_source_cards(source_card_id)")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_insights_explore ON insights(explore_id)")
    await conn.commit()
    # 4. File-canonical dir move cards/ → insights/ (idempotent).
    if data_root is not None:
        old, new = Path(data_root) / "cards", Path(data_root) / "insights"
        if old.exists() and not new.exists():
            old.rename(new)
```

> Note: modern SQLite (`legacy_alter_table` off, the default) auto-rewrites FK references in `insight_stats` when `cards`→`insights`. We `DROP reviews` before anything else so its FK to `cards` is gone. Index recreation tolerates the case where `insights` doesn't exist yet on a partial state (guarded by IF NOT EXISTS + the rename above running first in the same call).

- [ ] **Step 2: Write `migrations/v3/init_database.py`** (full fresh-install snapshot AS OF v3). Compose it by taking the **v2 full schema** (read `migrations/v2/init_database.py` + the v1 tables it builds on) and applying: rename the 3 card tables → insight*, **omit the `reviews` CREATE + its 2 indexes**, omit `reviews.explore_id`, use index names `idx_insights_created`/`idx_insight_source`/`idx_insights_explore`. Keep `sessions`, `explores`, `recall_event`, `search_log` unchanged. Export `TABLES`, `INDEXES`, `async def run(conn, *, data_root=None)` matching the v1/v2 module shape.

- [ ] **Step 3: Write the test** `memorytalk/tests/migration/v3_insight_rename/test.py`:
```python
"""v3_insight_rename — rename cards→insights, drop reviews; fresh init. See README.md."""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v1 import init_database as v1_init
from memorytalk.migrations.v2 import up_database as v2_up
from memorytalk.migrations.v3 import up_database as v3_up
from memorytalk.migrations.v3 import init_database as v3_init


async def _tables(conn):
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_v3_up_renames_and_drops(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)
    await v2_up.run(conn, data_root=None)
    # seed a card row so we can prove data survives the rename
    await conn.execute(
        "INSERT INTO cards (card_id, insight, rounds, tags, created_at) "
        "VALUES ('card_x','hi','[]','{}','t')")
    await conn.commit()
    await v3_up.run(conn, data_root=tmp_path)
    t = await _tables(conn)
    assert {"insights", "insight_stats", "insight_source_cards"} <= t
    assert "cards" not in t and "reviews" not in t and "card_stats" not in t
    async with conn.execute("SELECT insight FROM insights WHERE card_id='card_x'") as c:
        assert (await c.fetchone())[0] == "hi"   # data preserved, card_ id kept
    await conn.close()


@pytest.mark.asyncio
async def test_v3_up_idempotent(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)
    await v2_up.run(conn, data_root=None)
    await v3_up.run(conn, data_root=tmp_path)
    await v3_up.run(conn, data_root=tmp_path)   # second run must not error
    assert "insights" in await _tables(conn)
    await conn.close()


@pytest.mark.asyncio
async def test_v3_up_moves_file_dir(tmp_path):
    (tmp_path / "cards" / "01").mkdir(parents=True)
    (tmp_path / "cards" / "01" / "card_x").mkdir()
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)
    await v2_up.run(conn, data_root=None)
    await v3_up.run(conn, data_root=tmp_path)
    assert (tmp_path / "insights" / "01" / "card_x").exists()
    assert not (tmp_path / "cards").exists()
    await conn.close()


@pytest.mark.asyncio
async def test_v3_init_fresh_has_insight_tables_no_reviews():
    conn = await aiosqlite.connect(":memory:")
    await v3_init.run(conn, data_root=None)
    t = await _tables(conn)
    assert {"insights", "insight_stats", "insight_source_cards", "sessions",
            "explores", "recall_event", "search_log"} <= t
    assert "reviews" not in t and "cards" not in t
    await conn.close()
```

- [ ] **Step 4: Run** `pytest memorytalk/tests/migration/v3_insight_rename/test.py -v` — iterate until all pass (write up_database.py, then init_database.py).

- [ ] **Step 5: README + commit**
```bash
git add memorytalk/migrations/v3/__init__.py memorytalk/migrations/v3/init_database.py memorytalk/migrations/v3/up_database.py memorytalk/tests/migration/v3_insight_rename/
git commit -m "feat(migration): v3 db — rename card tables→insight, drop reviews, move file dir"
```

### Task 4: `migrations/v3` searchbase

**Files:**
- Create: `memorytalk/migrations/v3/init_searchbase.py`, `up_searchbase.py`
- Test: add to `tests/migration/v3_insight_rename/test.py` (or a sibling) using a `LocalSearchBackend` fixture.

- [ ] **Step 1: `up_searchbase.py`** (full code):
```python
"""v3 upgrade: rename the cards LanceDB collection → insights."""
from __future__ import annotations

from memorytalk.searchbase import AdminBackend


async def run(admin: AdminBackend, *, data_root=None) -> None:
    await admin.rename_collection("cards", "insights")   # idempotent
```

- [ ] **Step 2: `init_searchbase.py`** — mirror v1/v2's init_searchbase (it builds collections from `SCHEMAS`). After Task 5 renames the constant, `SCHEMAS` will hold `insights` + `rounds`, so a re-export of the current init is enough. For now write:
```python
"""v3 init searchbase: same builder as v1/v2 (collections come from SCHEMAS)."""
from __future__ import annotations

from memorytalk.migrations.v1.init_searchbase import run  # noqa: F401
```

- [ ] **Step 3: Test** — `admin.rename_collection` already covered in Task 1; add a focused test that `v3.up_searchbase.run(admin)` renames `cards`→`insights` on a backend seeded with a `cards` collection. Run it.

- [ ] **Step 4: Commit**
```bash
git add memorytalk/migrations/v3/init_searchbase.py memorytalk/migrations/v3/up_searchbase.py memorytalk/tests/migration/v3_insight_rename/
git commit -m "feat(migration): v3 searchbase — rename cards collection→insights"
```

---

## Phase C — App code: review retirement (do BEFORE the rename so renamed code is review-free)

### Task 5: Delete the review feature

**Files (delete):** `service/reviews.py`, `repository/reviews.py`, `api/reviews.py`, `cli/review.py`, `schemas/review.py`, `schemas/reviews.py`, `tests/api/test_reviews.py`.
**Files (edit — remove references, exact sites from the audit):**
- `repository/cards.py`: delete `_reviews_key` (47-48), `append_review_mirror` (74-78), `bump_review` (196-212); strip `reviews.jsonl` from the module docstring (1-10) + delete docstring (276-279).
- `service/read.py`: drop `Review` import (20), `reviews_rows = …list_for_card` (62), `reviews=[Review(**r) …]` (69).
- `service/cards.py`: drop `reviews_deleted = …delete_for_card` (211) and the `reviews_deleted` return key (235-239); update the delete docstring (189).
- `schemas/card.py`: drop `from …review import Review` (7) and `reviews: list[Review] = Field(...)` (56).
- `schemas/cards.py`: drop `reviews_deleted: int = 0` from `CardDeleteResponse` (70-82).
- `schemas/__init__.py`: drop the `review`/`reviews` imports + `__all__` entries.
- `service/__init__.py`: drop `ReviewService`/`ReviewServiceError`/`ReviewConflict` import + `__all__`.
- `repository/store.py`: drop `from …reviews import ReviewStore` (21) + `self.reviews = ReviewStore(conn)` (33).
- `api/__init__.py`: drop `app.state.reviews = ReviewService(...)` (139) and `"reviews"` from the router loop (203).
- `cli/__init__.py`: drop `"review"` from `_COMMANDS` (32).
- `cli/_format.py`: delete `fmt_review_created` (341).
- `cli/card.py`: delete the delete-preview review lines (196, 201).
- `tests/api/explores/association/test.py`: remove review-association assertions.

**Note (`insight_stats` review_* columns):** leave the `review_up/down/neutral/count` columns in place (vestigial, never written) — `CardStats`/`get_stats` keep reading them as 0. Do NOT drop columns.

- [ ] **Step 1:** Delete the 7 files (`git rm`).
- [ ] **Step 2:** Apply every edit above. Grep to confirm zero remaining references: `grep -rn "ReviewService\|ReviewStore\|reviews_deleted\|schemas.review\|append_review_mirror\|bump_review\|/reviews\b" memorytalk/ | grep -v tests/repository/v4` → expect empty (v4 reviews are separate and untouched).
- [ ] **Step 3:** Run `pytest memorytalk/tests -q`. Expect failures ONLY in the to-be-renamed card tests + any test asserting `reviews_deleted`; fix card tests' review expectations (remove them). The v4 suite must stay green.
- [ ] **Step 4: Commit**
```bash
git add -A
git commit -m "refactor(v3): retire unused review feature (service/api/cli/schema/store/tests)"
```

---

## Phase D — App code: card → insight rename (storage layer first)

### Task 6: searchbase_schema constant

**Files:** `service/searchbase_schema.py`; importers `service/cards.py:33`, `service/recall.py:34`, `service/search.py:31`, `tests/api/test_search.py:35`.

- [ ] **Step 1:** In `searchbase_schema.py`: `CARDS = "cards"` → `INSIGHTS = "insights"`; in `SCHEMAS` change the key `CARDS` → `INSIGHTS`. 
- [ ] **Step 2:** Update the 4 importers: `from …searchbase_schema import CARDS` → `INSIGHTS`; all `CARDS` uses → `INSIGHTS`.
- [ ] **Step 3:** `grep -rn "\bCARDS\b" memorytalk/ → empty`. Run `pytest memorytalk/tests/api/test_search.py -q`.
- [ ] **Step 4: Commit** `refactor(v3): searchbase collection constant CARDS→INSIGHTS="insights"`.

### Task 7: `repository/cards.py` → `repository/insights.py` (`InsightStore`)

**Files:** rename file; `repository/store.py` import+attr.

- [ ] **Step 1:** `git mv memorytalk/repository/cards.py memorytalk/repository/insights.py`.
- [ ] **Step 2:** In `insights.py`: `class CardStore` → `class InsightStore`; `PREFIX = "cards"` → `PREFIX = "insights"`; rewrite ALL SQL table literals `cards`→`insights`, `card_stats`→`insight_stats`, `card_source_cards`→`insight_source_cards` (audit lists every line: 107,119,135,141,154,171,190,207,225,233,245,266,269,272,325,339,366,388). Keep `card_id` column names. Update the module docstring's `cards/<bucket>/...` → `insights/<bucket>/...`.
- [ ] **Step 3:** `repository/store.py`: `from …cards import CardStore`→`from …insights import InsightStore`; `self.cards = CardStore(...)` → `self.insights = InsightStore(...)`. (Find every `db.cards.` / `.cards.` store reference across the codebase via grep and change to `.insights.`.)
- [ ] **Step 4:** `grep -rn "CardStore\|db\.cards\b\|self\.cards\b" memorytalk/ | grep -v v4 → empty`. Run `pytest memorytalk/tests/repository -q` + `memorytalk/tests/api/test_read.py -q`.
- [ ] **Step 5: Commit** `refactor(v3): CardStore→InsightStore; SQL+PREFIX→insight*`.

---

## Phase E — App code: schemas, service, api

### Task 8: schemas `Card*` → `Insight*`

**Files:** `git mv schemas/card.py schemas/insight.py`, `git mv schemas/cards.py schemas/insights.py`; `schemas/__init__.py`; importers `service/read.py`, `service/cards.py`, `api/cards.py`.

- [ ] **Step 1:** Rename classes: `SourceCard→SourceInsight`, `CardRound→InsightRound`, `CardStats→InsightStats`, `Card→Insight`; `CreateCardRequest→CreateInsightRequest`, `CreateCardResponse→CreateInsightResponse`, `CardMeta→InsightMeta`, `CardListResponse→InsightListResponse`, `CardDeleteResponse→InsightDeleteResponse`, `CardTagResponse→InsightTagResponse`. Keep field names (`card_id` etc.).
- [ ] **Step 2:** Update `schemas/__init__.py` imports + `__all__`; update every importer (grep `from memorytalk.schemas import ...Card`).
- [ ] **Step 3:** `grep -rn "\bCard\b\|\bCardStats\b\|CreateCardRequest\|CardMeta\|CardListResponse\|CardDeleteResponse\|CardTagResponse\|SourceCard\|CardRound" memorytalk/ | grep -v v4 → empty`. Run `pytest memorytalk/tests -q -k "read or insight or card"`.
- [ ] **Step 4: Commit** `refactor(v3): schemas Card*→Insight*`.

### Task 9: service `CardService`→`InsightService` + read path

**Files:** `git mv service/cards.py service/insights.py`; `service/read.py` (`read_card`→`read_insight`), `service/__init__.py`, `api/__init__.py` (`app.state.cards`→`app.state.insights`).

- [ ] **Step 1:** `class CardService`→`InsightService`, `CardServiceError`→`InsightServiceError`, `CardConflict`→`InsightConflict`, `CardNotFound`→`InsightNotFound`; events `card_*`→`insight_*` (verify `service/events.py` helper names; rename there too if defined).
- [ ] **Step 2:** `service/read.py`: `read_card`→`read_insight` (keep `card_id` param), `self.db.cards`→`self.db.insights`, `Card(...)`→`Insight(...)`. Update `api/read.py:24` to call `svc.read_insight(...)` (IdKind.CARD stays).
- [ ] **Step 3:** `api/__init__.py`: `app.state.cards = CardService(...)`→`app.state.insights = InsightService(...)`; update any `request.app.state.cards` readers (grep).
- [ ] **Step 4:** `grep -rn "CardService\|read_card\|app.state.cards\|state\.cards" memorytalk/ | grep -v v4 → empty`. Run `pytest memorytalk/tests/api/test_read.py memorytalk/tests/service -q`.
- [ ] **Step 5: Commit** `refactor(v3): CardService→InsightService; read_card→read_insight`.

### Task 10: api routes `/v3/cards`→`/v3/insights`

**Files:** `git mv api/cards.py api/insights.py`; `api/__init__.py` router registration (203).

- [ ] **Step 1:** In `api/insights.py`: routes `/cards`→`/insights`, `/cards/{card_id}/tags`→`/insights/{insight_id}/tags`, `/cards/{card_id}`→`/insights/{insight_id}` (path param name cosmetic; keep handler logic). Update imported schema names to `Insight*`.
- [ ] **Step 2:** `api/__init__.py`: the dynamic router loop — change `"cards"`→`"insights"` in the module name list (and confirm the module path `api/insights.py` resolves).
- [ ] **Step 3:** Run `pytest memorytalk/tests/api -q` (card API tests will be renamed in Task 12; for now expect those to fail on the old `/v3/cards` path — that's covered next).
- [ ] **Step 4: Commit** `refactor(v3): API /v3/cards→/v3/insights`.

---

## Phase F — CLI + tests + docs

### Task 11: CLI `card`→`insight`

**Files:** `git mv cli/card.py cli/insight.py`; `cli/_format.py` (fmt_card_*→fmt_insight_*); `cli/__init__.py` (_COMMANDS).

- [ ] **Step 1:** `@click.group("card")`→`@click.group("insight")`, `def card()`→`def insight()`, all `@card.command(...)`→`@insight.command(...)`; update API paths the CLI hits (`/v3/cards`→`/v3/insights`); docstrings card→insight.
- [ ] **Step 2:** `cli/_format.py`: `fmt_card_created/list/delete/tag`→`fmt_insight_*`; update callers in `cli/insight.py`.
- [ ] **Step 3:** `cli/__init__.py`: `_COMMANDS` — `"card"`→`"insight"` (and `"review"` already removed in Task 5).
- [ ] **Step 4:** `grep -rn "fmt_card_\|click.group(\"card\"\|\"card\"" memorytalk/cli → empty`. Run `pytest memorytalk/tests/cli -q` (card CLI tests renamed in Task 12).
- [ ] **Step 5: Commit** `refactor(v3): CLI card→insight command + fmt_card_*→fmt_insight_*`.

### Task 12: rename + fix tests

**Files:** `tests/api/test_cards*.py`→`test_insights*.py`, `tests/cli/test_card*`→`test_insight*` (enumerate via `ls`); update routes (`/v3/cards`→`/v3/insights`), class names (`Card*`→`Insight*`), store attrs (`.cards`→`.insights`), and any leftover review assertions.

- [ ] **Step 1:** `git mv` each card/insight test file. 
- [ ] **Step 2:** Update assertions/fixtures inside (routes, schema names, `.insights` store, drop review checks).
- [ ] **Step 3:** Run the FULL suite `pytest memorytalk/tests -q`. Fix every remaining failure until green. (The v4 suite must remain green throughout.)
- [ ] **Step 4: Commit** `test(v3): rename card tests→insight, update routes/schemas/store refs`.

### Task 13: doc sync

**Files:** `docs/works/v4/card.md` §9 (lines ~324/326/334/339 — reviews→insight_reviews → "drop reviews; v4 takes the name"); any `docs/structure/v3/talk-card.md` references that should note the rename.

- [ ] **Step 1:** Update §9 table + prose to match the finalized design (drop reviews, keep card_ ids, rename_collection). Remove the `insight_reviews` mentions and the id-rewrite "连带重写 insight_reviews" note.
- [ ] **Step 2:** `grep -rn "insight_reviews" docs/ → empty` (except historical/explicitly-archival mentions).
- [ ] **Step 3: Commit** `docs(v4): sync §9 with finalized insight migration (drop reviews)`.

---

## Phase G — Migration v4 (create v4 tables) + final verify

### Task 14: `migrations/v4` — create v4 tables

**Files:** Create `memorytalk/migrations/v4/{__init__.py,init_database.py,up_database.py,init_searchbase.py,up_searchbase.py}`; Test `tests/migration/v4_card_tables/{README.md,__init__.py,test.py}`.

**Interfaces — Consumes:** `memorytalk/repository/v4/schema.py` `create_v4_schema` / `V4_TABLES` / `V4_INDEXES` (built in Plan 1).

- [ ] **Step 1: `up_database.py`** (full code):
```python
"""v4 upgrade: create the 5 v4 card tables (cards/positions/reviews/card_links/card_sessions)."""
from __future__ import annotations

from memorytalk.repository.v4.schema import create_v4_schema


async def run(conn, *, data_root=None) -> None:
    await create_v4_schema(conn)   # idempotent (CREATE TABLE IF NOT EXISTS)
```

- [ ] **Step 2: `init_database.py`** — full snapshot AS OF v4 = the v3 snapshot + the v4 tables. Compose:
```python
"""v4 init: full schema snapshot (v3 insight schema + v4 card tables)."""
from __future__ import annotations

from memorytalk.migrations.v3 import init_database as v3_init
from memorytalk.repository.v4.schema import create_v4_schema


async def run(conn, *, data_root=None) -> None:
    await v3_init.run(conn, data_root=data_root)   # sessions/insights/explores/...
    await create_v4_schema(conn)                    # + cards/positions/reviews/card_links/card_sessions
```

- [ ] **Step 3: `init_searchbase.py` / `up_searchbase.py`** — v4 SQLite-only for now (the v4 LanceDB collections `cards`(issue)/`positions`(claim) are a later plan). Both no-ops:
```python
async def run(admin, *, data_root=None) -> None:
    return  # v4 searchbase collections land in a later plan
```

- [ ] **Step 4: Test** `tests/migration/v4_card_tables/test.py`:
```python
"""v4_card_tables — migration v4 creates the 5 v4 tables atop v3. See README.md."""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v3 import init_database as v3_init
from memorytalk.migrations.v4 import up_database as v4_up
from memorytalk.migrations.v4 import init_database as v4_init


async def _tables(conn):
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_v4_up_creates_v4_tables_on_v3():
    conn = await aiosqlite.connect(":memory:")
    await v3_init.run(conn, data_root=None)
    await v4_up.run(conn, data_root=None)
    t = await _tables(conn)
    assert {"cards", "positions", "reviews", "card_links", "card_sessions"} <= t
    assert {"insights", "insight_stats"} <= t   # v3 insight tables coexist
    await conn.close()


@pytest.mark.asyncio
async def test_v4_init_fresh_has_both():
    conn = await aiosqlite.connect(":memory:")
    await v4_init.run(conn, data_root=None)
    t = await _tables(conn)
    assert {"cards", "positions", "card_links", "card_sessions", "insights"} <= t
    await conn.close()
```

- [ ] **Step 5: Run + README + commit**
```bash
git add memorytalk/migrations/v4 memorytalk/tests/migration/v4_card_tables/
git commit -m "feat(migration): v4 — create the 5 v4 card tables (atop renamed insight schema)"
```

### Task 15: Full-suite + lifespan integration verify

- [ ] **Step 1:** `pytest memorytalk/tests -q` — entire suite green (v3 renamed, reviews gone, v4 tables + foundation intact).
- [ ] **Step 2:** Run the migration lifespan integration test (`tests/migration/lifespan_integration/`) — confirm a v2→v3→v4 catch-up applies cleanly and the app boots. If it constructs a real data_root, assert `cards/`→`insights/` move + collection rename happened.
- [ ] **Step 3:** Confirm the runner discovers v3+v4 (`discover_versions` returns `[v1,v2,v3,v4]`) and a fresh install runs only v4 init.
- [ ] **Step 4: Commit** any fixups: `test(v3/v4): full migration + rename suite green`.

---

## Self-Review

**1. Spec coverage** (vs `insight-migration.md`): rename 3 tables ✓ (Task 3); drop reviews + retire feature ✓ (Tasks 3,5); collection rename via primitive ✓ (Tasks 1,4); file dir move in migrations/ ✓ (Tasks 2,3); keep `card_` ids ✓ (global constraint; tests assert card_x preserved); CLI/API/class/schema rename ✓ (Tasks 7-12); v4 tables ✓ (Task 14); migration logic confined to `migrations/` ✓ (only `rename_collection` primitive + `data_root` plumbing live outside, both framework support). 

**2. Placeholder scan:** migrations/framework/tests have full code; rename/removal tasks give exact file:line + symbol maps + grep-to-zero verification + suite-green gates (mechanical transforms verified by the existing 589-test net, not reproduced verbatim — acceptable per the rename nature).

**3. Type consistency:** `INSIGHTS` constant (Task 6) used by `InsightStore`/services; `InsightStore` attr `db.insights` (Task 7) used by `read_insight` (Task 9); schema `Insight*` (Task 8) used by api/service; `create_v4_schema` (Plan 1) consumed by Task 14. `card_id` column + `CARD_PREFIX` + `IdKind.CARD` unchanged throughout (two-stage). Review symbols fully removed before rename (Task 5 precedes Tasks 6-12) so renamed modules are review-free.

**Open verification items flagged for execution (not assumptions):**
- Task 1: confirm `LocalAdminBackend._index` attrs (`db`, `data_dir`, internal tracking sets) + whether installed `lancedb` async exposes `rename_table` (fallback provided).
- Task 3 Step 2: the v3 `init_database` full snapshot must be composed from the actual v2 schema — read `migrations/v2/init_database.py` + the v1 tables it builds on; this plan specifies the delta, not the full DDL.
- Task 5: verify `service/explores.py` (or explore association) has no hard dependency on the `reviews` table before dropping (audit flagged it as "likely OK, verify").
- Task 9: confirm `service/events.py` card_* event helper names to rename.
