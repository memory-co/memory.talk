"""SyncWatcher — drives adapters into IngestService under a cursor.

Architecture:

- Sync owns the upstream-state cursor (sha256 + last_round_id + line
  offset) in its own ``sync.db`` (``repository.sync_checkpoint``).
  IngestService owns the persisted memory data — it knows nothing about
  sync's cursors.
- One ``PollingObserver`` (watchdog) handles filesystem events, bridging
  them into the asyncio loop via ``loop.call_soon_threadsafe``. Polling
  is portable; we can swap to a native observer per-platform later.
- A single worker task drains the event queue, debounces same-path
  bursts, and calls ``_sync_one_source`` — the **same** path used by
  the cold-scan backfill loop. There is exactly one place where "decide
  what's new and send it to ingest" logic lives.

Sync flow (``_sync_one_source``):

  1. ``adapter.probe(source_id)``   — get sha256 + session_id + metadata
  2. checkpoint sha matches?        — skip; file unchanged
  3. ``ingest.ensure_session()``    — what's the server's current cursor?
  4. ``adapter.read_after(...)``    — pull rounds strictly after that cursor
  5. ``ingest.append_rounds(...)``  — append with optimistic concurrency
  6. on conflict, ask adapter for rounds after server's actual cursor,
     retry once; on second conflict, log and give up this round
  7. update checkpoint to new (sha, last_round_id, line_offset)

Backfill on watcher start is exactly "iterate ``adapter.list_sources()``
and run step 1-7 on each". Live watchdog events are exactly "run step
1-7 on the touched path". Same code, same logging, same observability.
"""
from __future__ import annotations
import asyncio
import collections
import datetime as _dt
import logging
import time
from pathlib import Path
from typing import Iterable

from memorytalk.adapters import ADAPTERS, BaseAdapter
from memorytalk.config import Config
from memorytalk.repository.sync_checkpoint import SyncCheckpointStore
from memorytalk.schemas import (
    AppendRoundsRequest, AppendRoundsResponse,
    EnsureSessionRequest, SourceProbe,
)
from memorytalk.service.sessions import IngestService


_ISO = lambda: _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

_watch_log = logging.getLogger("memorytalk.sync.watch")


class SyncWatcher:
    def __init__(
        self,
        config: Config,
        ingest: IngestService,
        checkpoints: SyncCheckpointStore,
        adapters: Iterable[BaseAdapter] | None = None,
        debounce_ms: int | None = None,
    ):
        self.config = config
        self.ingest = ingest
        self.checkpoints = checkpoints
        self.adapters: list[BaseAdapter] = (
            list(adapters)
            if adapters is not None
            else _build_adapters_from_settings(config)
        )
        self.debounce_seconds = (debounce_ms or config.settings.sync.debounce_ms) / 1000.0

        self.running: bool = False
        # "stopped" before start; "backfilling" during cold scan;
        # "watching" once backfill finishes and the observer is steady state.
        self.phase: str = "stopped"
        self._start_ts: float | None = None
        self._observer = None  # watchdog Observer (lazy import)
        self._queue: asyncio.Queue[tuple[BaseAdapter, Path]] | None = None
        self._worker_task: asyncio.Task | None = None
        self._backfill_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_at: dict[Path, float] = {}
        self._totals = _new_totals()
        self._recent: collections.deque[dict] = collections.deque(maxlen=20)
        self._last_run: dict | None = None

    # ────────── public reads ──────────

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
        """Return ``{"_total": {...flat counters...}, "<endpoint>": {...}}``.

        ``_total`` is the cross-endpoint sum; per-endpoint slices key
        on ``<source>@<label>``. Layout is nested so a future caller
        can render either the unified or per-endpoint view without
        re-summing.
        """
        return dict(self._totals)

    def endpoint_info(self) -> list[dict]:
        """Per-endpoint metadata for ``/v3/sync/status.endpoints``."""
        out: list[dict] = []
        for a in self.adapters:
            ok = True
            reason: str | None = None
            roots = a.watch_roots()
            if roots:
                # File-based adapter — endpoint OK iff at least one
                # watch root exists. HTTP adapters return [] and are
                # always reported ``ok=True`` (network reachability
                # would need an actual probe call we don't want to
                # do on every status request).
                ok = any(p.exists() for p in roots)
                reason = None if ok else "missing"
            out.append({
                "source": a.source_name,
                "location": a.location,
                "label": a.label,
                "ok": ok,
                "reason": reason,
            })
        return out

    def recent(self, limit: int = 5) -> list[dict]:
        return list(reversed(list(self._recent)))[:limit]

    def last_run(self) -> dict | None:
        return self._last_run

    # ────────── lifecycle ──────────

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

        # Observer + worker FIRST so live events arriving during backfill
        # queue here and don't get dropped.
        self._observer = _make_observer(self)
        if self._observer is not None:
            self._observer.start()
        self._worker_task = asyncio.create_task(self._worker_loop())

        self._backfill_task = asyncio.create_task(self._run_backfill())

        _watch_log.info(
            "watcher started adapters=%s watching=%s",
            self.adapter_names(),
            [str(p) for a in self.adapters for p in a.watch_roots()],
        )
        return {
            "status": "started",
            "phase": "backfilling",
            "adapters": self.adapter_names(),
        }

    async def _run_backfill(self) -> None:
        """Cold-scan every adapter's known sources. Per-adapter try/except
        so one broken adapter doesn't kill the rest."""
        _watch_log.info("backfill start adapters=%s", self.adapter_names())
        try:
            for adapter in self.adapters:
                ep = _endpoint_key(adapter)
                try:
                    count = 0
                    for probe in adapter.list_sources():
                        stats = await self._sync_one_source(adapter, probe.source_id)
                        _accumulate(self._totals, stats, endpoint=ep)
                        count += 1
                    _watch_log.info(
                        "backfill endpoint=%s sources=%d totals=%s",
                        ep, count, dict(self._totals.get("_total", {})),
                    )
                except Exception as e:
                    _watch_log.exception(
                        "backfill failed endpoint=%s", ep,
                    )
                    self._record_error(
                        adapter.source_name, f"backfill: {e}", endpoint=ep,
                    )
                    continue
        finally:
            self.phase = "watching"
            _watch_log.info(
                "backfill finished, phase=watching totals=%s",
                self._totals.get("_total", {}),
            )

    async def pause(self) -> None:
        if not self.running:
            return
        await self._teardown()

    async def _teardown(self) -> tuple[dict, float]:
        uptime = self.uptime_seconds
        start_iso = _dt.datetime.fromtimestamp(
            time.time() - uptime, tz=_dt.UTC,
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        stop_iso = _ISO()

        self.running = False
        self.phase = "stopped"

        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=1.0)
            except Exception:
                pass
            self._observer = None

        if self._backfill_task:
            self._backfill_task.cancel()
            try:
                await self._backfill_task
            except (asyncio.CancelledError, Exception):
                pass
            self._backfill_task = None

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass
            self._worker_task = None

        totals = dict(self._totals)
        # ``last_run.totals`` only carries the cross-endpoint summary
        # for backward compat with the old _IngestStats shape; the
        # per-endpoint breakdown lives in this lifespan's running
        # ``self._totals`` until the next start() resets it.
        self._last_run = {
            "start": start_iso, "stop": stop_iso,
            "duration_seconds": uptime,
            "totals": totals.get("_total", _zero_counters()),
        }
        self._start_ts = None
        _watch_log.info(
            "watcher stopped uptime=%.1fs totals=%s",
            uptime, totals.get("_total", {}),
        )
        return totals, uptime

    # ────────── inbound from watchdog ──────────

    def on_event(self, adapter: BaseAdapter, path: Path) -> None:
        if not self.running or self._loop is None or self._queue is None:
            _watch_log.debug(
                "event dropped (watcher idle) adapter=%s path=%s",
                adapter.source_name, path,
            )
            return
        _watch_log.info("event adapter=%s path=%s", adapter.source_name, path)
        self._loop.call_soon_threadsafe(self._enqueue, adapter, path)

    def _enqueue(self, adapter: BaseAdapter, path: Path) -> None:
        if self._queue is None:
            return
        self._pending_at[path] = time.monotonic()
        try:
            self._queue.put_nowait((adapter, path))
        except asyncio.QueueFull:
            pass

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        while True:
            adapter, path = await self._queue.get()
            await self._await_settled(path)
            ep = _endpoint_key(adapter)
            try:
                stats = await self._sync_one_source(adapter, str(path))
                _accumulate(self._totals, stats, endpoint=ep)
            except Exception as e:
                _watch_log.exception(
                    "worker iteration failed endpoint=%s path=%s",
                    ep, path,
                )
                self._record_error(path, str(e), endpoint=ep)

    async def _await_settled(self, path: Path) -> None:
        """Wait until the path hasn't been re-touched for one debounce window."""
        deadline = self._pending_at.get(path, 0.0) + self.debounce_seconds
        while True:
            now = time.monotonic()
            if now >= deadline:
                self._pending_at.pop(path, None)
                return
            await asyncio.sleep(max(0.01, deadline - now))
            deadline = self._pending_at.get(path, 0.0) + self.debounce_seconds

    # ────────── core sync path (shared by backfill + watcher) ──────────

    async def _sync_one_source(self, adapter: BaseAdapter, source_id: str) -> dict:
        # Per-source counters are flat — the caller folds them into
        # self._totals (nested by endpoint) via _accumulate().
        stats = _zero_counters()
        ep = _endpoint_key(adapter)  # "source@label"

        # 1. Probe
        try:
            probe = adapter.probe(source_id)
        except Exception as e:
            _watch_log.exception(
                "probe failed endpoint=%s source=%s", ep, source_id,
            )
            self._record_error(source_id, f"probe: {e}", endpoint=ep)
            stats["errors"] = 1
            return stats
        if probe is None:
            return stats
        stats["discovered"] = 1

        # Mint canonical session_id once; everywhere below uses this.
        # probe.session_id is the raw upstream id; the minted id embeds
        # (source, location) via loc_code so two endpoints can carry
        # the same upstream id without colliding.
        sid = adapter.mint_session_id(probe.session_id)

        # 2. Checkpoint short-circuit (scoped by source+location+raw id)
        ckpt = await self.checkpoints.get(
            adapter.source_name, adapter.location, probe.session_id,
        )
        if ckpt and ckpt["sha256"] == probe.sha256:
            stats["skipped"] = 1
            return stats

        # 3. Ask ingest where its cursor is — pass the already-minted
        # canonical id (sessions table row keyed by it).
        try:
            ensure = await self.ingest.ensure_session(EnsureSessionRequest(
                source=adapter.source_name, session_id=sid,
                location=adapter.location, location_label=adapter.label,
            ))
        except Exception as e:
            _watch_log.exception("ensure_session failed sid=%s", sid)
            self._record_error(sid, f"ensure: {e}", endpoint=ep)
            stats["errors"] = 1
            return stats
        server_last = ensure.last_round_id
        hint_offset = ckpt["line_offset"] if ckpt else 0

        # 4. Read incremental rounds from the source
        try:
            batch = adapter.read_after(
                source_id,
                after_round_id=server_last,
                hint_line_offset=hint_offset,
            )
        except Exception as e:
            _watch_log.exception("read_after failed sid=%s", sid)
            self._record_error(sid, f"read_after: {e}", endpoint=ep)
            stats["errors"] = 1
            return stats

        # 5 + 6. Append, retry once on conflict
        if batch.rounds:
            result, used_offset = await self._send_with_conflict_retry(
                adapter, probe, sid, batch, expected_prev=server_last,
            )
            if result is None:
                stats["errors"] = 1
                return stats
            new_last = result.new_last_round_id
            appended = result.appended_count
        else:
            # No new content but file sha changed (e.g. metadata-only
            # rewrite) — bump the checkpoint sha so next time we
            # short-circuit.
            result = None
            new_last = server_last
            appended = 0
            used_offset = batch.next_line_offset

        # 7. Update checkpoint
        await self.checkpoints.upsert(
            source=adapter.source_name,
            location=adapter.location,
            session_id=probe.session_id,
            sha256=probe.sha256,
            last_round_id=new_last,
            line_offset=used_offset,
            updated_at=_ISO(),
        )

        if appended > 0:
            if server_last is None:
                stats["imported"] = 1
                self._record(sid, "imported", rounds=appended, endpoint=ep)
            else:
                stats["appended"] = 1
                self._record(sid, "rounds_appended", rounds=appended, endpoint=ep)
            _watch_log.info(
                "ingested endpoint=%s sid=%s appended=%d new_last=%s",
                ep, sid, appended, new_last,
            )
        else:
            stats["skipped"] = 1

        # Vector-index outcome is independent from the append path —
        # see docs/report/2026-05-23-search-vector-index-batch-gap.md.
        if result is not None and getattr(result, "index_status", "ok") != "ok":
            stats["index_errors"] = 1
            self._record(
                sid,
                "index_partial" if result.index_status == "partial" else "index_failed",
                indexed=result.indexed_count,
                index_failed=result.index_failed_count,
                error=result.index_error,
                endpoint=ep,
            )

        return stats

    async def _send_with_conflict_retry(
        self,
        adapter: BaseAdapter,
        probe: SourceProbe,
        sid: str,
        batch,
        expected_prev: str | None,
    ) -> tuple[AppendRoundsResponse | None, int]:
        """Returns (response, line_offset_used). ``sid`` is the canonical
        minted session_id (passes straight to ingest)."""
        req = AppendRoundsRequest(
            session_id=sid,
            source=adapter.source_name,
            location=adapter.location,
            location_label=adapter.label,
            expected_prev_round_id=expected_prev,
            rounds=batch.rounds,
            created_at=probe.created_at,
            metadata=probe.metadata,
        )
        result = await self.ingest.append_rounds(req)
        if result.status == "ok":
            return result, batch.next_line_offset

        _watch_log.warning(
            "append conflict sid=%s expected=%s actual=%s; retrying once",
            sid, expected_prev, result.actual_last_round_id,
        )

        # Re-read from the server's actual cursor.
        try:
            retry_batch = adapter.read_after(
                probe.source_id,
                after_round_id=result.actual_last_round_id,
                hint_line_offset=0,
            )
        except Exception:
            _watch_log.exception("re-read after conflict failed sid=%s", sid)
            return None, batch.next_line_offset

        if not retry_batch.rounds:
            _watch_log.info(
                "post-conflict file has nothing new sid=%s; cursor caught up", sid,
            )
            return AppendRoundsResponse(
                status="ok",
                session_id=sid,
                new_last_round_id=result.actual_last_round_id,
                appended_count=0,
                round_count=0,
            ), retry_batch.next_line_offset

        retry_req = AppendRoundsRequest(
            session_id=sid,
            source=adapter.source_name,
            location=adapter.location,
            location_label=adapter.label,
            expected_prev_round_id=result.actual_last_round_id,
            rounds=retry_batch.rounds,
            created_at=probe.created_at,
            metadata=probe.metadata,
        )
        retry_result = await self.ingest.append_rounds(retry_req)
        if retry_result.status == "ok":
            return retry_result, retry_batch.next_line_offset

        _watch_log.error(
            "conflict persists after retry sid=%s actual=%s",
            sid, retry_result.actual_last_round_id,
        )
        self._record_error(sid, "conflict persists",
                           endpoint=_endpoint_key(adapter))
        return None, retry_batch.next_line_offset

    # ────────── recent ring buffer ──────────

    def _record(self, session_id: str, event: str, **extra) -> None:
        self._recent.append({
            "at": _ISO(), "session_id": session_id, "event": event, **extra,
        })

    def _record_error(self, key, msg: str, *, endpoint: str = "") -> None:
        self._recent.append({
            "at": _ISO(), "session_id": str(key), "event": "error",
            "error": msg, "endpoint": endpoint,
        })


def _endpoint_key(adapter: BaseAdapter) -> str:
    """Display key for an adapter instance: ``"<source>@<label>"``. Used
    in event records + ``totals`` per-endpoint aggregation."""
    return f"{adapter.source_name}@{adapter.label or adapter.location}"


_COUNTER_KEYS = (
    "discovered", "imported", "appended", "skipped",
    "overwrite_warnings", "errors", "index_errors",
)


def _zero_counters() -> dict:
    return {k: 0 for k in _COUNTER_KEYS}


def _new_totals() -> dict:
    """Watcher totals layout. ``_total`` is the cross-endpoint sum
    consumed by old callers that just want one number per counter;
    per-endpoint slices live under their ``<source>@<label>`` key.
    Empty per-endpoint dict initially — slices spring into existence
    on first event from that endpoint."""
    return {"_total": _zero_counters()}


def _accumulate(totals: dict, delta: dict, endpoint: str | None = None) -> None:
    """Add ``delta`` into ``totals['_total']`` and the per-endpoint
    slice keyed by ``endpoint`` (created lazily). Unknown delta keys
    are ignored so adding new counters in the future doesn't blow up
    on older watcher instances mid-upgrade."""
    for k, v in delta.items():
        if k not in _COUNTER_KEYS:
            continue
        totals["_total"][k] = totals["_total"].get(k, 0) + v
        if endpoint:
            slice_ = totals.setdefault(endpoint, _zero_counters())
            slice_[k] = slice_.get(k, 0) + v


def _make_observer(watcher: SyncWatcher):
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers.polling import PollingObserver
    except ImportError:
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


def _build_adapters_from_settings(config: Config) -> list[BaseAdapter]:
    """Materialize adapter instances per ``settings.sync.endpoints``.

    When ``endpoints`` is None (default), auto-detect: instantiate every
    registered adapter whose ``DEFAULT_LOCATION`` exists on disk. This
    keeps a fresh install zero-config — claude-code at ``~/.claude``
    and codex at ``~/.codex/sessions`` get picked up if present, no
    user action required. Remote endpoints (openclaw etc.) MUST be
    listed explicitly because they have no default.
    """
    eps = config.settings.sync.endpoints
    if eps is not None:
        # Explicit list — instantiate exactly what user asked for.
        out: list[BaseAdapter] = []
        for ep in eps:
            cls = ADAPTERS.get(ep.source)
            if cls is None:
                _watch_log.warning(
                    "settings.sync.endpoints references unknown source=%r; skipping",
                    ep.source,
                )
                continue
            try:
                # Pass through adapter-specific extras (auth_key etc.).
                extras = {
                    k: v for k, v in ep.model_dump().items()
                    if k not in {"source", "location", "label"} and v is not None
                }
                out.append(cls(location=ep.location, label=ep.label, **extras))
            except Exception:
                _watch_log.exception(
                    "failed to instantiate adapter %s@%s",
                    ep.source, ep.location,
                )
        return out

    # Auto-detect: register a default-location instance per adapter whose
    # location exists. Adapters without a DEFAULT_LOCATION (HTTP-only,
    # e.g. openclaw) are skipped — they need explicit settings.
    auto: list[BaseAdapter] = []
    for cls in ADAPTERS.values():
        default = getattr(cls, "DEFAULT_LOCATION", None)
        if not default:
            continue
        if not Path(default).expanduser().exists():
            continue
        try:
            auto.append(cls(location=default))
        except Exception:
            _watch_log.exception("auto-detect failed for %s", cls.source_name)
    return auto
