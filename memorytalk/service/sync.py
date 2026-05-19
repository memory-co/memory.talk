"""SyncWatcher — backend service that observes adapter roots and drives ingest.

Architecture:

- One watchdog ``PollingObserver`` instance, shared across adapters. Polling
  is portable; if/when we want native FS events we can swap to ``Observer``
  per platform. Polling cadence is debounce_ms.
- Each adapter contributes ``watch_roots()`` directories. Missing dirs
  don't crash — they show up in status with ``ok: false / reason: missing``.
- File events go into an ``asyncio.Queue`` via a thread-safe bridge
  (``loop.call_soon_threadsafe``).
- One async worker drains the queue, debounces same-path events, calls
  the matching adapter's ``convert_file``, then dispatches into the
  ``IngestService`` directly (in-process — no HTTP roundtrip).
- ``running`` flag + ``sync_state.json`` persist across server restarts.
- ``recent`` is a small ring buffer (≤ 20) for ``GET /v3/sync/status``;
  full history lives in ``ingest_log`` + ``events.jsonl``.
"""
from __future__ import annotations
import asyncio
import collections
import datetime as _dt
import json
import time
from pathlib import Path
from typing import Iterable

from memorytalk.adapters import ADAPTERS, BaseAdapter
from memorytalk.config import Config
from memorytalk.schemas import IngestSessionRequest, RoundInput
from memorytalk.service.sessions import IngestService


_ISO = lambda: _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class SyncState:
    """Persisted (across server restarts) sync state — just the enabled flag."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        if not self.path.exists():
            return {"enabled": False}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {"enabled": False}

    def save(self, enabled: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"enabled": enabled}))


class SyncWatcher:
    def __init__(
        self,
        config: Config,
        ingest: IngestService,
        adapters: Iterable[BaseAdapter] | None = None,
        debounce_ms: int | None = None,
    ):
        self.config = config
        self.ingest = ingest
        # Use every registered adapter by default.
        self.adapters: list[BaseAdapter] = (
            list(adapters)
            if adapters is not None
            else [cls() for cls in ADAPTERS.values()]
        )
        self.debounce_seconds = (debounce_ms or config.settings.sync.debounce_ms) / 1000.0
        self.state = SyncState(config.sync_state_path)

        self.running: bool = False
        self._start_ts: float | None = None
        self._observer = None  # watchdog Observer (lazy import)
        self._queue: asyncio.Queue[tuple[BaseAdapter, Path]] | None = None
        self._worker_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_at: dict[Path, float] = {}
        # totals over current start→stop window
        self._totals = _new_totals()
        # ring buffer of recent events
        self._recent: collections.deque[dict] = collections.deque(maxlen=20)
        # last completed (start, stop, totals) run — for `stopped` status output
        self._last_run: dict | None = None

    # ────────── public lifecycle ──────────

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_ts if self._start_ts else 0.0

    def adapter_names(self) -> list[str]:
        return [a.source_name for a in self.adapters]

    def watching(self) -> list[dict]:
        out: list[dict] = []
        for a in self.adapters:
            for p in a.watch_roots():
                exists = p.exists()
                out.append({
                    "path": str(p),
                    "ok": exists,
                    "reason": None if exists else "missing",
                })
        return out

    def totals(self) -> dict:
        return dict(self._totals)

    def recent(self, limit: int = 5) -> list[dict]:
        # The deque keeps newest at the right (we append). Return newest-first.
        return list(reversed(list(self._recent)))[:limit]

    def last_run(self) -> dict | None:
        return self._last_run

    async def start(self) -> dict:
        """Start the watcher. Idempotent: returns ``already_running`` if running.

        Returns a dict matching :class:`SyncStartResponse` payload shape.
        """
        if self.running:
            return {
                "status": "already_running",
                "adapters": self.adapter_names(),
                "uptime_seconds": self.uptime_seconds,
            }

        self.running = True
        self._start_ts = time.monotonic()
        self._totals = _new_totals()
        self._recent.clear()
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self.state.save(enabled=True)

        # ── 1. Backfill (initial discovery) ────────────────────────────
        backfill = _new_totals()
        for a in self.adapters:
            for payload in a.iter_sessions():
                stats = await self._ingest_one(payload)
                _accumulate(backfill, stats)
        self._totals = dict(backfill)  # totals carries backfill counts forward

        # ── 2. Watcher (PollingObserver) ───────────────────────────────
        self._observer = _make_observer(self)
        if self._observer is not None:
            self._observer.start()

        # ── 3. Worker ─────────────────────────────────────────────────
        self._worker_task = asyncio.create_task(self._worker_loop())

        return {
            "status": "started",
            "adapters": self.adapter_names(),
            "backfill": backfill,
        }

    async def stop(self) -> dict:
        """Explicit user-initiated stop. Clears the persisted enable flag —
        the server won't auto-resume the watcher on next start."""
        if not self.running:
            return {"status": "not_running"}
        totals, uptime = await self._teardown()
        self.state.save(enabled=False)
        return {"status": "stopped", "uptime_seconds": uptime, "totals": totals}

    async def pause(self) -> None:
        """Graceful shutdown without flipping the persisted flag.

        Used by the FastAPI lifespan exit so that the next server start
        auto-resumes the watcher (the user's last explicit choice stands).
        No-op if not running.
        """
        if not self.running:
            return
        await self._teardown()

    async def _teardown(self) -> tuple[dict, float]:
        """Common teardown: stop observer + worker; record last_run.

        Returns (totals snapshot, uptime seconds).
        """
        uptime = self.uptime_seconds
        start_iso = _dt.datetime.fromtimestamp(
            time.time() - uptime, tz=_dt.UTC,
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        stop_iso = _ISO()

        self.running = False

        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=1.0)
            except Exception:
                pass
            self._observer = None

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass
            self._worker_task = None

        totals = dict(self._totals)
        self._last_run = {
            "start": start_iso, "stop": stop_iso,
            "duration_seconds": uptime, "totals": totals,
        }
        self._start_ts = None
        return totals, uptime

    # ────────── inbound from watchdog (threaded) ──────────

    def on_event(self, adapter: BaseAdapter, path: Path) -> None:
        """Called from the watchdog thread via the bridging handler."""
        if not self.running or self._loop is None or self._queue is None:
            return
        # Bounce to the event loop. Idempotent — multiple events for the same
        # file path collapse via the queue's worker debounce.
        self._loop.call_soon_threadsafe(self._enqueue, adapter, path)

    def _enqueue(self, adapter: BaseAdapter, path: Path) -> None:
        if self._queue is None:
            return
        self._pending_at[path] = time.monotonic()
        try:
            self._queue.put_nowait((adapter, path))
        except asyncio.QueueFull:
            pass  # impossible (unbounded), but defensive

    # ────────── worker ──────────

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        while True:
            adapter, path = await self._queue.get()
            # Coalesce: if newer events for this path are in the queue,
            # wait for things to settle before processing.
            await self._await_settled(path)

            try:
                payload = adapter.convert_file(path)
            except Exception as e:
                self._record_error(path, str(e))
                continue
            if payload is None:
                continue
            stats = await self._ingest_one(payload)
            _accumulate(self._totals, stats)

    async def _await_settled(self, path: Path) -> None:
        """Wait until the file hasn't been re-touched for one debounce window."""
        deadline = self._pending_at.get(path, 0.0) + self.debounce_seconds
        while True:
            now = time.monotonic()
            if now >= deadline:
                self._pending_at.pop(path, None)
                return
            await asyncio.sleep(max(0.01, deadline - now))
            deadline = self._pending_at.get(path, 0.0) + self.debounce_seconds

    # ────────── ingest one payload ──────────

    async def _ingest_one(self, payload: dict) -> dict:
        """Dispatch a dict payload through IngestService; return per-call stats."""
        stats = _new_totals()
        try:
            req = IngestSessionRequest(
                session_id=payload["session_id"],
                source=payload["source"],
                created_at=payload.get("created_at") or "",
                metadata=payload.get("metadata") or {},
                sha256=payload["sha256"],
                rounds=[RoundInput(**r) for r in payload.get("rounds") or []],
            )
            resp = await self.ingest.ingest(req)
        except Exception as e:
            stats["errors"] = 1
            self._record_error(payload.get("session_id", "?"), str(e))
            return stats

        action = resp.action
        if action == "imported":
            stats["discovered"] = 1
            stats["imported"] = 1
            self._record(resp.session_id, "imported", rounds=resp.round_count)
        elif action == "appended":
            stats["discovered"] = 1
            stats["appended"] = 1
            self._record(resp.session_id, "rounds_appended", rounds=resp.added_count)
        elif action == "partial_append":
            stats["discovered"] = 1
            stats["appended"] = 1
            stats["overwrite_warnings"] = 1
            self._record(
                resp.session_id, "rounds_overwrite_skipped",
                rounds_skipped=len(resp.overwrite_skipped or []),
            )
        else:  # skipped
            stats["discovered"] = 1
            stats["skipped"] = 1
        return stats

    # ────────── recent ring buffer ──────────

    def _record(self, session_id: str, event: str, **extra) -> None:
        self._recent.append({
            "at": _ISO(), "session_id": session_id, "event": event, **extra,
        })

    def _record_error(self, key: str, msg: str) -> None:
        self._recent.append({
            "at": _ISO(), "session_id": str(key), "event": "error", "error": msg,
        })


def _new_totals() -> dict:
    return {
        "discovered": 0, "imported": 0, "appended": 0,
        "skipped": 0, "overwrite_warnings": 0, "errors": 0,
    }


def _accumulate(totals: dict, delta: dict) -> None:
    for k, v in delta.items():
        totals[k] = totals.get(k, 0) + v


def _make_observer(watcher: SyncWatcher):
    """Build a watchdog observer wired to push events into ``watcher.on_event``.

    Uses the polling observer for portability. Missing roots are logged as
    ``watching[].ok == False`` but don't fail the start.
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers.polling import PollingObserver
    except ImportError:
        # watchdog not installed → no observer; sync still works as a manual
        # one-shot via `sync start` (does backfill once and then idles).
        return None

    class _Handler(FileSystemEventHandler):
        def __init__(self, adapter: BaseAdapter):
            self.adapter = adapter

        def on_modified(self, event):
            if event.is_directory:
                return
            watcher.on_event(self.adapter, Path(event.src_path))

        def on_created(self, event):
            if event.is_directory:
                return
            watcher.on_event(self.adapter, Path(event.src_path))

    observer = PollingObserver(timeout=watcher.debounce_seconds)
    for adapter in watcher.adapters:
        for root in adapter.watch_roots():
            if root.exists():
                observer.schedule(_Handler(adapter), str(root), recursive=True)
    return observer
