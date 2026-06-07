"""file_logging — searchbase 三类操作各自落独立文件. See README.md."""
from __future__ import annotations

import logging

import pytest

from memorytalk.config import Config
from memorytalk.searchbase import Doc, Query
from memorytalk.searchbase.local._logging import setup_file_logging
from memorytalk.tests.searchbase.local.conftest import make_backend


# ── Per-test handler isolation ──
#
# Python's logger registry is process-wide. Each test in this file
# points setup_file_logging at a fresh tmp_path — without explicit
# cleanup, leftover handlers (from this file OR from other test files
# that boot a real backend) sit around and the idempotency check makes
# the next test's setup a no-op, leaving its log files empty. Clearing
# tagged handlers BOTH before and after each test restores per-test
# isolation regardless of which file ran previously.

def _drop_searchbase_handlers() -> None:
    for category in ("maintenance", "query", "index"):
        logger = logging.getLogger(f"memorytalk.searchbase.{category}")
        for h in list(logger.handlers):
            if getattr(h, "_searchbase_tag", None) is not None:
                logger.removeHandler(h)
                h.close()


@pytest.fixture(autouse=True)
def _isolate_searchbase_handlers():
    _drop_searchbase_handlers()
    yield
    _drop_searchbase_handlers()


@pytest.fixture
async def backend_with_logs(data_root, tmp_path):
    """Backend whose three log files live under an isolated tmp_path
    so tests don't share log state."""
    config = Config(data_root)
    config.ensure_dirs()
    log_dir = tmp_path / "searchbase_logs"
    b = await make_backend(
        config, collections={"cards": {"fields": {}}}, log_dir=log_dir,
    )
    try:
        yield b, log_dir
    finally:
        await b.close()


# ────────── setup contract ──────────

async def test_setup_creates_three_log_files(tmp_path):
    log_dir = tmp_path / "logs"
    setup_file_logging(log_dir)
    for category in ("maintenance", "query", "index"):
        logging.getLogger(f"memorytalk.searchbase.{category}").info(
            "hello from %s", category,
        )
    for category in ("maintenance", "query", "index"):
        path = log_dir / f"{category}.log"
        assert path.exists(), f"missing {path}"


async def test_setup_is_idempotent(tmp_path):
    """Re-running setup_file_logging on the same dir must NOT stack
    duplicate handlers — otherwise tests + long-lived servers leak
    handlers + write each line N times."""
    log_dir = tmp_path / "logs"
    setup_file_logging(log_dir)
    setup_file_logging(log_dir)
    setup_file_logging(log_dir)
    logger = logging.getLogger("memorytalk.searchbase.maintenance")
    tagged = [h for h in logger.handlers if getattr(h, "_searchbase_tag", None)]
    assert len(tagged) == 1


async def test_setup_silences_propagation(tmp_path, caplog):
    """propagate=False so root-level handlers (including pytest's
    caplog or stdout-bound ones) don't see these messages."""
    log_dir = tmp_path / "logs"
    setup_file_logging(log_dir)
    caplog.set_level(logging.DEBUG)
    logging.getLogger("memorytalk.searchbase.query").info("don't bubble")
    assert not any("don't bubble" in r.message for r in caplog.records)


# ────────── per-category routing through the backend ──────────

async def test_search_writes_to_query_log(backend_with_logs):
    backend, log_dir = backend_with_logs
    await backend.upsert("cards", [Doc(id="c1", text="hello")])
    await backend.search("cards", Query(text="hello", top_k=5))
    for category in ("query", "index"):
        for h in logging.getLogger(
            f"memorytalk.searchbase.{category}"
        ).handlers:
            h.flush()
    qlog = (log_dir / "query.log").read_text()
    assert "query coll=cards" in qlog
    assert "top_k=5" in qlog


async def test_upsert_writes_to_index_log(backend_with_logs):
    backend, log_dir = backend_with_logs
    await backend.upsert("cards", [
        Doc(id="c1", text="hi"), Doc(id="c2", text="bye"),
    ])
    for h in logging.getLogger("memorytalk.searchbase.index").handlers:
        h.flush()
    ilog = (log_dir / "index.log").read_text()
    assert "upsert coll=cards docs=2" in ilog


async def test_delete_writes_to_index_log(backend_with_logs):
    backend, log_dir = backend_with_logs
    await backend.upsert("cards", [Doc(id="c1", text="hi")])
    await backend.delete("cards", ["c1"])
    for h in logging.getLogger("memorytalk.searchbase.index").handlers:
        h.flush()
    ilog = (log_dir / "index.log").read_text()
    assert "delete coll=cards ids=1" in ilog


async def test_compaction_writes_to_maintenance_log(backend_with_logs):
    """The maintenance loop already runs at startup; force an explicit
    compact_all so the assertion isn't racing the loop's startup tick."""
    backend, log_dir = backend_with_logs
    await backend._maintenance.compact_all()
    for h in logging.getLogger(
        "memorytalk.searchbase.maintenance"
    ).handlers:
        h.flush()
    mlog = (log_dir / "maintenance.log").read_text()
    assert "compaction done" in mlog


# ────────── inter-category isolation ──────────

async def test_search_does_not_pollute_index_or_maintenance_log(backend_with_logs):
    """One concern per file. A search must not write to index.log /
    maintenance.log even though all three loggers share the same logger
    tree under memorytalk.searchbase."""
    backend, log_dir = backend_with_logs
    await backend.upsert("cards", [Doc(id="c1", text="x")])
    # Snapshot the OTHER logs *after* upsert (which legitimately writes
    # to index.log) but *before* the search.
    ilog_before = (log_dir / "index.log").read_text()
    mlog_before = (log_dir / "maintenance.log").read_text()
    await backend.search("cards", Query(text="x", top_k=3))
    for category in ("query", "index", "maintenance"):
        for h in logging.getLogger(
            f"memorytalk.searchbase.{category}"
        ).handlers:
            h.flush()
    assert (log_dir / "index.log").read_text() == ilog_before
    assert (log_dir / "maintenance.log").read_text() == mlog_before
