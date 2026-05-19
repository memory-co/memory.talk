# Sync as a settings-driven switch

**Date:** 2026-05-19
**Status:** Approved (pending spec review)

## Goal

Reshape `sync` from a CLI control plane into a settings-driven background
service.

- One CLI verb only: `memory-talk sync` → shows status.
- On/off lives in `settings.json` (`sync.enabled`); `setup` asks for it.
- Server start is never blocked by initial backfill — backfill runs as a
  background task with progress visible in `sync` status.

## Motivation

The current `memory-talk sync start` runs the full initial backfill
inside the HTTP request handler. With many adapter-discovered sessions
this exceeds the CLI's 30s timeout, so the user sees:

```
error: cannot reach server: timed out
```

despite the server actually being reachable and the backfill still in
progress. The same code path runs in the FastAPI lifespan on auto-resume,
so `server start` itself hangs whenever sync was previously enabled.

`sync start` / `sync stop` are also a duplicate control surface — the
state is already persisted across restarts via `sync_state.json`. The
durable thing is a settings choice, not a daemon command.

## Scope

In scope:

1. Add `sync.enabled: bool` to `SyncConfig` in `settings.json`.
2. Migrate the existing `~/.memory-talk/sync_state.json` into
   `settings.json` transparently, then delete the old file.
3. Drop `memory-talk sync start` / `memory-talk sync stop` CLI commands.
   `memory-talk sync` becomes a single-shot status display.
4. Drop `POST /v3/sync/start` and `POST /v3/sync/stop` API routes.
   `GET /v3/sync/status` stays.
5. `setup` wizard adds a Sync section that prompts for `sync.enabled`.
6. Refactor `SyncWatcher.start()` to schedule backfill as an `asyncio`
   task. Start observer + worker *before* backfill so live events during
   the backfill window aren't dropped (safe: `_ingest_one` is
   content-hash idempotent — see `service/sessions.py:154-167`).
7. Surface backfill progress via a new `phase` field
   (`backfilling` | `watching`) on the status payload.
8. Per-session ingest errors during backfill are caught, recorded in the
   `recent` ring buffer via `_record_error("<adapter>", "backfill: ...")`,
   and the loop continues to the next session.

Out of scope:

- Hot reload of `sync.enabled` without server restart (Settings are
  reloaded on server (re)start today; sync follows the same model).
- `--wait` flag on any command to block until backfill completes (status
  polling is the answer if you want this).
- Backfill cancellation.

## Design

### Settings schema (`memorytalk/config.py`)

```python
class SyncConfig(BaseModel):
    enabled: bool = False     # NEW — the durable on/off switch
    debounce_ms: int = 200
```

Default `False` for the model — but `setup` defaults the prompt to
`True` on first install (see below). Both defaults exist for a reason:
the model default makes test fixtures and ad-hoc config files
conservative, while the wizard default reflects the common-user intent
("I installed memory-talk to sync my sessions").

### Migration of `sync_state.json`

In `Config._load_settings()`, after reading `settings.json`:

```
if sync_state.json exists and parsed settings["sync"] lacks "enabled":
    legacy_enabled = read sync_state.json → enabled (default False)
    settings["sync"]["enabled"] = legacy_enabled
    write_settings_atomic(...)
    delete sync_state.json
```

Idempotent and one-shot. New installs never see the legacy file and skip
this branch entirely. Once migrated, `SyncState` and
`Config.sync_state_path` are deleted.

### CLI: `memorytalk/cli/sync.py`

Replace the `@click.group()` + three subcommands with a single
`@click.command("sync")` that prints status. `--json` and `--limit`
options carry over.

Concretely:

```python
@click.command("sync")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
@click.option("--limit", type=int, default=5,
              help="Recent-events tail size (default 5)")
def sync(json_out: bool, limit: int) -> None:
    """Show backend sync status."""
    _call("GET", "/v3/sync/status", json_out, fmt_sync_status,
          params={"limit": str(limit)})
```

Top-level CLI registration switches from `main.add_command(sync_group)` to
`main.add_command(sync)`.

### Setup wizard (`memorytalk/cli/setup.py`)

A new `section("Sync")` block between Server and the diff/persist step:

```python
section("Sync")
old_sync = base.get("sync") or {}
enabled_default = old_sync.get("enabled", True if is_first_install else False)
sync_enabled = console.confirm(
    "Enable backend sync? (auto-ingest Claude Code sessions etc.)",
    default=enabled_default,
)
new["sync"] = {
    "enabled": sync_enabled,
    "debounce_ms": old_sync.get("debounce_ms", 200),
}
```

The existing carry-over loop at `setup.py:127` drops `"sync"` from its
key list (since we now build it explicitly).

`diff_settings` picks up the change → `_maybe_start_or_restart` offers
"Restart now?" when the user flipped it.

### `SyncWatcher.start()` refactor (`memorytalk/service/sync.py`)

```python
async def start(self) -> dict:
    if self.running:
        return {
            "status": "already_running",
            "phase": self.phase,
            "adapters": self.adapter_names(),
            "uptime_seconds": self.uptime_seconds,
        }

    self.running = True
    self.phase = "backfilling"
    self._start_ts = time.monotonic()
    self._totals = _new_totals()
    self._recent.clear()
    self._loop = asyncio.get_running_loop()
    self._queue = asyncio.Queue()

    # Observer + worker FIRST. Live events arriving during backfill
    # enqueue here; the worker may double-process files that the
    # backfill loop is about to touch, but _ingest_one is content-hash
    # idempotent so duplicates are no-ops.
    self._observer = _make_observer(self)
    if self._observer is not None:
        self._observer.start()
    self._worker_task = asyncio.create_task(self._worker_loop())

    # Backfill in the background — return immediately.
    self._backfill_task = asyncio.create_task(self._run_backfill())

    return {
        "status": "started",
        "phase": "backfilling",
        "adapters": self.adapter_names(),
    }


async def _run_backfill(self) -> None:
    try:
        for adapter in self.adapters:
            for payload in adapter.iter_sessions():
                try:
                    stats = await self._ingest_one(payload)
                    _accumulate(self._totals, stats)
                except Exception as e:
                    self._record_error(adapter.name, f"backfill: {e}")
    finally:
        self.phase = "watching"
```

Per-session try/except gives resilience: a poisoned session can't kill
the entire backfill. The error is captured in the `recent` ring buffer
so `sync` status shows it.

`SyncWatcher.__init__` no longer takes a `SyncState`. `pause()` and
`_teardown()` keep working as-is for graceful server shutdown. `stop()`
becomes private (`_stop_internal`) or is deleted entirely — without the
CLI command and `state.save(False)` call there's no remaining caller.

### Lifespan (`memorytalk/api/__init__.py`)

```python
# OLD
if app.state.sync.state.load().get("enabled"):
    try:
        await app.state.sync.start()
    except Exception as e:
        print(f"[memory-talk] auto-resume sync failed: {e}", file=sys.stderr)

# NEW
if config.settings.sync.enabled:
    try:
        await app.state.sync.start()   # now fast — schedules backfill
    except Exception as e:
        print(f"[memory-talk] sync auto-start failed: {e}", file=sys.stderr)
```

The shutdown path still calls `app.state.sync.pause()`.

### Status payload (`memorytalk/api/sync.py`)

```python
@router.get("/sync/status")
async def get_sync_status(request: Request, limit: int = Query(5, ge=0, le=20)):
    config = request.app.state.config
    if not config.settings.sync.enabled:
        return {"status": "disabled"}
    watcher = request.app.state.sync
    if not watcher.running:
        return {"status": "error", "error": "watcher not running"}
    return {
        "status": "running",
        "phase": watcher.phase,
        "uptime_seconds": watcher.uptime_seconds,
        "adapters": watcher.adapter_names(),
        "watching": watcher.watching(),
        "totals": watcher.totals(),
        "last_event_at": (watcher.recent(1) or [{}])[0].get("at"),
        "recent": watcher.recent(limit=limit),
    }
```

`fmt_sync_status` renders `phase` when present, with a hint line:

```
sync · running · phase backfilling · 142 ingested · last event 2s ago
```

When `status == "disabled"`:

```
sync · disabled
hint: rerun `memory-talk setup` to enable
```

### Removed code

- `memorytalk/cli/sync.py`: `sync` group, `sync_start`, `sync_stop`
- `memorytalk/cli/_format.py`: `fmt_sync_start`, `fmt_sync_stop`
- `memorytalk/api/sync.py`: `post_sync_start`, `post_sync_stop`
- `memorytalk/service/sync.py`: `SyncState` class, `SyncWatcher.state`
  attribute, `stop()` public method (or keep + repurpose; see Open
  Questions)
- `memorytalk/config.py`: `Config.sync_state_path`
- Any test fixture or smoke test referencing the removed entry points

## Testing

New / updated tests:

- `test_smoke.py`: top-level help no longer asserts `start`/`stop` under
  `sync`; one `sync` command exists.
- Setup wizard non-TTY smoke: extend the canned stdin script to answer
  the new Sync prompt; assert `settings.json["sync"]["enabled"]` matches
  the input.
- `tests/service/test_sync.py` (new or extended):
  - `start()` returns within ~10ms even with a fake adapter that yields
    1000 sessions (backfill is backgrounded).
  - Per-session ingest error → an error entry appears in `recent` (via
    the existing `_record_error` helper) and the loop continues to the
    next session.
  - `phase` transitions `backfilling` → `watching` after the task
    finishes.
- `tests/api/test_sync.py` (new or extended):
  - `sync.enabled=false` → `GET /v3/sync/status` returns
    `{"status": "disabled"}` (200).
  - Removed `POST /sync/start` returns 404 / 405.
- Migration test: pre-seed a `sync_state.json` with `enabled: true` and
  a settings.json missing `sync.enabled` → after `Config()` load,
  settings has `enabled=true` and `sync_state.json` is gone.

## Docs

- `README.md`: update sync section. CLI surface is `memory-talk sync`
  (status). Configuration via `memory-talk setup` or by editing
  `settings.json["sync"]["enabled"]` and restarting the server.
- `docs/cli/v3/sync.md` (if present): rewrite. Otherwise add one.
- `docs/cli/v3/setup.md`: list the new Sync section.

## Open Questions

1. **Keep `SyncWatcher.stop()` public?** Today it's called only by
   `memory-talk sync stop`, which we're deleting. The internal
   `_teardown` / `pause` covers shutdown. Recommendation: delete
   `stop()` entirely. (Decide at implementation time; not load-bearing
   for the design.)

2. **Wizard Sync section default in "modify" mode** when the existing
   settings.json doesn't yet have `sync.enabled` (legacy users who
   haven't been migrated through `_load_settings` yet, which shouldn't
   happen but defensively): fall back to the value from
   `sync_state.json` if present, else `False`. Migration in
   `_load_settings` should cover this; the wizard fallback is a belt
   and suspenders.

## Risks

- **Backfill error visibility.** A failing adapter could spam the
  `recent` ring buffer with error entries and push useful events out.
  Mitigation: capping consecutive errors per adapter (deferred — add
  only if it shows up in practice).
- **Observer-before-backfill ordering.** Relies on content-hash idempotency
  in `IngestService`. If that property regresses in the future,
  backfill + observer will double-ingest. Mitigation: keep the comment
  in `SyncWatcher.start()` explicit about the contract, and a test that
  asserts a re-ingest of the same payload is a no-op.
- **`sync.enabled` flipped in `settings.json` by hand.** Takes effect on
  next server (re)start, same as every other settings field. Documented
  behavior; `setup` is the discoverable path.
