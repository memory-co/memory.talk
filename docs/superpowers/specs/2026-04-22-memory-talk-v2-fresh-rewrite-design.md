# memory.talk v2 — Fresh Rewrite Design

**Date:** 2026-04-22
**Status:** Approved, ready for implementation planning
**Scope:** Delete the existing `memory_talk/` package and reimplement v2 in a new top-level `memory_talk_v2/` package, following `docs/api/v2/`, `docs/cli/v2/`, and `docs/structure/v2/` as the behavioral spec.

## 0. Goal and non-goals

**Goal.** Produce a runnable v2 (all endpoints + CLI) as one contiguous rewrite. v1 is deleted wholesale. Reusable logic (DSL parser, embedding providers, LanceDB wrapper, FTS snippet, claude-code adapter) is ported into the new package layout, not re-derived from scratch.

**Non-goals.**
- No data migration from v1 data roots. A v2 server refuses to start against a data root that shows v1 artifacts.
- No support for running v1 and v2 side by side.
- No `MEMORY_TALK_CLI_VERSION` dispatch — the `memory-talk` entrypoint is v2.
- No `codex` / `openclaw` sync adapters in this rewrite (interface stays; implementations deferred).

## 1. Package layout

```
memory_talk_v2/
├── __init__.py                    # package marker
├── __main__.py                    # python -m memory_talk_v2 → cli.main
├── config.py                      # Settings (incl. SearchConfig), Config, validate() w/ v1-residue detection
├── ids.py                         # new_card_id / new_session_id helpers, prefix_session_id, parse_id, Id kinds
├── models.py                      # Pydantic shared models (Round, Card, Session, Link, LinkRef, SearchLog, EventLog)
├── embedding.py                   # ported from v1 + validate_embedder() startup check
├── dsl.py                         # ported from v1 + added `source` field
│
├── storage/
│   ├── __init__.py
│   ├── schema.py                  # all v2 DDL; init_sqlite_schema(conn)
│   ├── sqlite.py                  # SQLiteStore — CRUD for sessions / rounds / cards / links / ingest_log / search_log / event_log
│   ├── lancedb.py                 # ported from v1: cards hybrid + sessions FTS
│   ├── files.py                   # sessions/, cards/, links/ on-disk read/write
│   └── jsonl_writer.py            # DatedJsonlWriter (logs/search, logs/events)
│
├── service/
│   ├── __init__.py
│   ├── sessions.py                # ingest: sha256-dedupe, index assignment, overwrite detection
│   ├── cards.py                   # validate rounds, expand, default links, vectorize, events
│   ├── links.py                   # user link creation (two-end events)
│   ├── tags.py                    # add/remove with diff-based event emission
│   ├── search.py                  # hybrid cards + FTS sessions + DSL whitelist + SearchLog
│   ├── view.py                    # prefix dispatch + TTL refresh
│   ├── log.py                     # event stream query
│   ├── rebuild.py                 # jsonl/file replay → clean SQLite + LanceDB
│   ├── ttl.py                     # current_ttl / refresh
│   ├── events.py                  # EventWriter (jsonl + event_log dual write, jsonl first)
│   └── snippet.py                 # ported from v1 (jieba-tokenize query, regex highlight)
│
├── api/
│   ├── __init__.py                # create_app(config) — validate, init schema, validate_embedder, mount routes
│   ├── status.py                  # GET  /v2/status
│   ├── sessions.py                # POST /v2/sessions
│   ├── cards.py                   # POST /v2/cards
│   ├── links.py                   # POST /v2/links
│   ├── tags.py                    # POST /v2/tags/add, /v2/tags/remove
│   ├── search.py                  # POST /v2/search
│   ├── view.py                    # POST /v2/view
│   ├── log.py                     # POST /v2/log
│   └── rebuild.py                 # POST /v2/rebuild
│
├── cli/
│   ├── __init__.py                # Click root command group; main()
│   ├── _http.py                   # api(method, path, **body) — shared HTTP client
│   ├── server.py                  # server start / stop / status
│   ├── search.py view.py log.py card.py tag.py link.py sync.py rebuild.py
│   └── _format.py                 # --format json|text helper
│
├── adapters/
│   ├── __init__.py
│   ├── base.py                    # BaseAdapter.iter_sessions(root) -> Iterator[SessionPayload]
│   └── claude_code.py             # ported from v1
│
└── tests/
    ├── __init__.py
    ├── conftest.py                # tmp_data_root, dummy_config, app_client, populated_* fixtures
    ├── unit/                      # pure-function tests (ids, ttl, dsl, snippet, jsonl_writer, embedding)
    ├── service/                   # real SQLite + LanceDB + dummy embedder, per service file
    ├── api/                       # FastAPI TestClient, one file per endpoint group
    └── e2e/                       # subprocess server + end-to-end smoke
```

**Packaging.** `pyproject.toml` switches `[project.scripts]` to `memory-talk = memory_talk_v2.cli:main`. `[tool.setuptools.packages.find]` includes `memory_talk_v2` and excludes `memory_talk_v2.tests*` so tests do not ship to site-packages. The old `memory_talk/` directory, `tests/` directory at the repo root, and `memory_talk.egg-info/` are deleted in the first commit of the rewrite.

## 2. Data layout and storage model

### 2.1 Data root

Default `~/.memory-talk/`, overridable via `--data-root` / `MEMORY_TALK_DATA_ROOT`. The contents are:

```
~/.memory-talk/
├── settings.json
├── memory.db
├── vectors/{cards,sessions}.lance/
├── sessions/{source}/{id[0:2]}/{sess_*}/{meta.json, rounds.jsonl}
├── cards/{id[0:2]}/{card_*}.json
├── links/{id[0:2]}/{link_*}.json
├── logs/search/YYYY-MM-DD.jsonl
├── logs/events/YYYY-MM-DD.jsonl
└── server.pid
```

**File layer is source of truth. SQLite is derived.** `/v2/rebuild` drops and rebuilds `memory.db` + `vectors/*.lance` from files. Each write: file first (atomic rename for single-object files, append for jsonl) → then SQLite → then vector. If SQLite or vector write fails partway, rebuild restores.

### 2.2 v1-residue detection

`Config.validate()` on startup inspects `memory.db` (if it exists) via `sqlite_master` and rejects the data root if any v1-only table is present (e.g., `recall_log`, or the v1 shape of `sessions` if detectable). A dedicated `ConfigValidationError` is raised from `create_app`; the uvicorn child exits nonzero, and the CLI's `server start` wrapper surfaces the error in its `{"status":"failed"}` payload. No auto-migration.

### 2.3 SQLite schema

```sql
sessions      (session_id PK, source, created_at, synced_at, metadata JSON, tags JSON, round_count)
rounds        (PK (session_id, idx), round_id, parent_id, timestamp, speaker, role,
               content JSON, is_sidechain, cwd, usage JSON)
cards         (card_id PK, summary, rounds JSON, created_at, expires_at)
links         (link_id PK, source_id, source_type, target_id, target_type, comment,
               expires_at NULLABLE, created_at)
ingest_log    (session_id, sha256, synced_at)
search_log    (search_id PK, query, where_dsl, top_k, created_at, response_json)
event_log     (event_id PK, object_id, object_kind, at, kind, detail JSON)

-- indexes
rounds      (session_id, round_id)
links       (source_id); links(target_id)
event_log   (object_id, at)
search_log  (created_at)
```

**No SQLite FTS.** All text search is in LanceDB. Column name for session round index is `idx` (SQL reserved word avoidance); round payload uses `index` in API / JSON.

**Default link encoding.** `links.expires_at IS NULL` means "default link (ttl=0 sentinel, never refresh, lives with parent card)". User links always have a non-null `expires_at`.

### 2.4 LanceDB tables

| Table | Columns | Search mode |
|---|---|---|
| `cards.lance` | `card_id`, `text` (jieba-segmented summary + rounds text), `vector` (embedding of summary) | FTS + vector hybrid with RRF reranker (v1's `hybrid_search_cards`) |
| `sessions.lance` | `session_id`, `text` (jieba-segmented round text, whole session) | Pure FTS (v1's `fts_search_sessions`), no vector |

Only cards are embedded. Sessions are FTS-only — inherited from v1.

### 2.5 DSL evaluation pattern

v1's pattern: DSL compiled to SQLite parameterized WHERE → produces `card_id` / `session_id` whitelist → LanceDB applies whitelist as pre-filter. v2 inherits this. The only DSL change is adding `source` as a filterable field (sessions-side only; cards have no `source`).

### 2.6 Snippets

`service/snippet.py` ported from v1 unchanged: jieba-tokenize the query, regex-highlight matches in the source text with `**…**`. Not using any FTS engine's built-in `snippet()` function.

## 3. Endpoint semantics — design decisions

Behavior defined in `docs/api/v2/`. This section records the non-obvious decisions made during design review and not fully pinned down by the spec docs.

### 3.1 `POST /v2/sessions` (ingest)

- `rounds.jsonl` is **append-only forever**. Overwrite-detected rounds are **not rewritten**; their original `idx` continues to point at the original content. This guarantees stability of `{session_id, idx}` references from cards.
- Content equality for overwrite detection compares `content` (JSON blob) + `role` + `speaker`. `timestamp` differences alone do not count as overwrite.
- `action` values: `imported`, `appended`, `skipped` (sha256 unchanged), `partial_append` (both appends and skips happened).
- `rounds_overwrite_skipped` event is emitted once per ingest with `detail.indexes` = list of skipped indexes.

### 3.2 `POST /v2/cards`

- Validation-before-write: any invalid index / prefix / monotonicity error → 400, nothing is written.
- Side-effect order: **file → SQLite → vector → events**. If vector write fails, the card file and SQLite row stand; rebuild will restore the vector. If an event write fails, the object stands; lifecycle log has a gap.
- Default links: one per distinct `session_id` in `rounds`. Written as separate `links/*.json` files with `expires_at = NULL` and recorded in SQLite with null `expires_at`.
- `card_extracted` event (session-side) is merged per session. If a card's `rounds` references the same session twice (e.g., `"11-15"` and `"20,22"`), one event with `indexes = "11-15,20,22"` is emitted for that session.
- `from_search_id` (optional on request) is passed through into the `card.created` event detail.

### 3.3 `POST /v2/links`

- Self-loop check (`source_id == target_id`) is explicit, returns 400.
- `comment` length bounded by `settings.search.comment_max_length`.
- Two events emitted per link creation: one `linked` on source with `direction=outgoing`, one on target with `direction=incoming`. Different `event_id`s. Each references the same `link_id`.

### 3.4 `POST /v2/tags/{add,remove}`

- Only accepts `sess_*` ids. `card_*` → 400 with `type mismatch`.
- Events are per-tag-actually-changed. Idempotent no-ops (already-present add, missing-from-list remove) do not emit.
- Response `tags` field returns the full tag list after the operation, not the diff.

### 3.5 `POST /v2/search`

- Empty query string is a valid input (metadata-only filter path). When `query == ""`, skip FTS/vector and sort whitelist by `created_at DESC`, take top_k.
- Links in search hits are filtered to `ttl >= 0` only. Expired user links (`ttl < 0`) are suppressed (they still appear via `view`).
- Every call appends the full response body to `search_log` table and `logs/search/YYYY-MM-DD.jsonl`. No event_log rows — `search_log` is search's own audit channel.
- `search_id` lives in the response and in `search_log`; the caller is free to drop it. It is only used for back-referencing via `cards.from_search_id` → `card.created.detail`.

### 3.6 `POST /v2/view`

- Prefix dispatches: `card_*` → card path, `sess_*` → session path, else 400.
- TTL refresh on card view: `expires_at = now + min((expires_at - now) * ttl.card.factor, ttl.card.max)`. If already expired (`remaining <= 0`), **do not refresh** — a dead card stays dead.
- User links attached to the viewed object are refreshed (same formula, `ttl.link.factor`/`max`). Default links (`expires_at IS NULL`) are not refreshed. Expired user links are returned in the response but not refreshed.
- No event is emitted for `view`, no jsonl append, no session TTL change. Sessions are permanent.

### 3.7 `POST /v2/log`

- Read-only. No TTL refresh, no event emission.
- Rows sorted by `at ASC`. `detail` is the parsed JSON object, not the raw string.

## 4. Cross-cutting mechanics

### 4.1 TTL

Stored as absolute `expires_at` ISO-8601 string. Never decremented on a timer — reads compute `ttl = expires_at - now`.

```python
def current_ttl(expires_at, now) -> int:
    if expires_at is None:         # default link sentinel
        return 0
    return int((iso_to_dt(expires_at) - now).total_seconds())

def refresh(expires_at, factor, max_seconds, now) -> str:
    remaining = (iso_to_dt(expires_at) - now).total_seconds()
    if remaining <= 0:             # already expired — do not refresh
        return expires_at
    new_remaining = min(remaining * factor, max_seconds)
    return dt_to_iso(now + timedelta(seconds=new_remaining))
```

### 4.2 EventWriter (dual write, jsonl first)

```python
def emit(object_id, kind, detail, at=None):
    event_id   = new_event_id()           # evt_<ULID>
    object_kind = "card" if startswith("card_") else "session"
    row = {event_id, object_id, object_kind, at, kind, detail}
    jsonl.append(row)                     # 1) jsonl first (crash-safe, truth of record)
    sqlite.insert(event_log, row)         # 2) sqlite
```

Reasoning: rebuild replays from jsonl, so as long as jsonl is written the event is not lost. If jsonl fails, we surface the error to the caller and do not pretend the write succeeded.

### 4.3 IDs

- `new_card_id()` / `new_link_id()` / `new_search_id()` / `new_event_id()` return `{prefix}{ULID}`.
- `prefix_session_id(platform_id)` is idempotent: if already prefixed, return as-is; else add `sess_`. Used once, at ingest boundary.
- `parse_id(s) -> (IdKind, raw)` for dispatch; `InvalidIdError` on unknown prefix.

## 5. Ops

### 5.1 Embedding startup validation

Inside `api/__init__.py::create_app`:
1. `config.validate()` — data root sanity, v1 residue detection.
2. `init_sqlite_schema(db_path)`.
3. `embedder = make_embedder(settings.embedding)`.
4. `validate_embedder(embedder)` — dummy trivially OK; local loads the model; openai checks env var presence and issues a `ping` embed probe, asserting `dim` matches `settings.embedding.dim`.
5. Mount routes.

On `EmbedderValidationError`, `create_app` raises; the uvicorn child exits nonzero; the CLI's `server start` wrapper reads stderr and returns `{"status":"failed","error":"…"}` with exit code 1.

### 5.2 `/v2/rebuild`

1. Drop all SQLite v2 tables + drop both LanceDB tables.
2. Walk `sessions/` — re-insert sessions + rounds; add to `sessions.lance`.
3. Walk `cards/` — re-insert cards; re-embed summary; add to `cards.lance`.
4. Walk `links/` — re-insert links (preserves `expires_at` from file, null for defaults).
5. Replay `logs/search/*.jsonl` in lexicographic (= date) order into `search_log`.
6. Replay `logs/events/*.jsonl` likewise into `event_log`. Malformed lines are skipped and counted into `errors_count` in the response.
7. `ensure_fts_index("cards", replace=True)` and same for `sessions`.
8. If `settings.search.search_log_retention_days > 0`, delete `logs/**/*.jsonl` files whose mtime is older than N days. Whole-file granularity, no in-file scan.

Object TTLs (`cards.expires_at`, `links.expires_at`) are read from the source files unchanged — rebuild does not reset time.

### 5.3 CLI

- All commands default to JSON output (`ensure_ascii=False`); `-f text` is a human-readable rendering.
- Only `sync` reads filesystem content directly — everything else is a thin wrapper around the local HTTP API via `cli/_http.py`.
- `server start` spawns a uvicorn subprocess, waits ~1s, and reports `started` / `failed` / `already_running` based on the subprocess state and an optional `GET /v2/status` probe.
- `server stop` reads `server.pid`, sends SIGTERM, removes the pid file.

### 5.4 `sync`

- Resolves an `adapters.BaseAdapter` by source name (default `claude-code`).
- Iterates `adapter.iter_sessions(platform_root)` producing a `SessionPayload` dict matching `POST /v2/sessions` body.
- For each payload, POSTs to `/v2/sessions`. Aggregates `imported / appended / skipped / partial_append / errors` counts.
- v1's `adapters/claude_code.py` is ported — mapping from Claude Code `.jsonl` files into `SessionPayload`.
- `codex` and `openclaw` adapter modules are not created in this rewrite. `BaseAdapter` is defined and `claude_code.py` implements it; adding another platform later is drop-in.

## 6. Testing strategy

`memory_talk_v2/tests/` organized by layer, not by scenario:

| Layer | Characteristics |
|---|---|
| `unit/` | No IO, pure functions. `test_ids`, `test_ttl`, `test_dsl`, `test_snippet`, `test_jsonl_writer`, `test_embedding` |
| `service/` | Real SQLite + LanceDB + dummy embedder; per-service file covering the service's own responsibilities |
| `api/` | FastAPI `TestClient` against `create_app(dummy_config)`; one file per endpoint group, exercises request validation and response shape |
| `e2e/` | Subprocess-launched uvicorn server, shells `memory-talk` CLI, runs a multi-step script (sync → card → search → view → log) |

**Coverage requirements baked into the plan:**
- Every event kind listed in `docs/api/v2/log.md` has at least one test that triggers it and asserts both the jsonl line and the `event_log` row.
- TTL has tests for: initial creation, refresh on view, already-expired no-refresh, default-link sentinel (always 0).
- Ingest has a test per `action` value (`imported`, `appended`, `skipped`, `partial_append`).
- DSL has happy-path tests for each operator (`=`, `!=`, `LIKE`, `IN`, `NOT IN`, `AND`, reltime) + one syntax-error test.

No network in any test. OpenAI embedding's `validate_embedder` is unit-tested with `httpx` patched.

## 7. Deletion and migration

**Removed in the rewrite:**
- `memory_talk/` (entire v1 package)
- `tests/` at the repo root (entire v1 test suite)
- `memory_talk.egg-info/`
- `MEMORY_TALK_CLI_VERSION` version dispatch
- `recall` command and corresponding service
- Any "v1 session tag / card read / card list / link list" CLI surface

**Updated in the rewrite:**
- `pyproject.toml` — entrypoint, package discovery, test path
- `README.md` — top-level reference to the v2 CLI
- `CLAUDE.md` — project-level instructions (if anything references v1 internals)
- `AGENTS.md` / `GEMINI.md` — same, if needed

**Not touched:**
- `docs/` (v2 spec), `skills/`, `hooks/`, `stories/`

## 8. Open risks

- **LanceDB FTS index invalidation.** v1 has a workaround (`ensure_fts_index` with append detection). Ported as-is; if it has latent bugs they come with.
- **jieba startup cost.** First `jieba.cut` after process start pays a one-time dictionary load. Acceptable for CLI / server; tests should share jieba via process-level import (pytest handles this naturally).
- **rebuild wall-clock.** For large data roots, rebuild is O(N) over file count and re-embeds every card. Blocking is documented in spec. No async / progress channel in this rewrite.
- **Two-end events** are written sequentially (outgoing then incoming). A crash between them leaves a single-ended `linked` event. Acceptable — rebuild does not reconstruct missing events.

---

## Implementation staging (to be detailed in the plan)

The plan document (written next, via the `writing-plans` skill) will sequence this rewrite as:

1. **Foundation.** Delete v1; new package skeleton; config + v1-residue check; ids; models; embedding + validate_embedder; dsl port (+ `source`); jsonl_writer; SQLite schema; lancedb port; snippet port; FastAPI app factory; `/v2/status`; CLI `server start/stop/status`; pyproject.toml swap.
2. **Writes.** sessions ingest, cards create, links create, tags add/remove; EventWriter; CLI `card`, `tag`, `link`, `sync` + claude_code adapter.
3. **Reads.** search + SearchLog persistence; view + TTL refresh; log; CLI `search`, `view`, `log`.
4. **Ops.** rebuild; retention; e2e tests.

Each stage commits independently and runs the full test suite green before proceeding.
