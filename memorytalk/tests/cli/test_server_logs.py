"""Tests for the daemon log pipeline.

We don't spawn the real daemon here — these tests exercise the pieces
in isolation:

- ``build_log_config`` + ``dictConfig`` actually wires the
  ``memorytalk``/``uvicorn`` loggers to a rotating file handler.
- ``memory.talk server logs`` reads from the configured path and
  handles the "no log yet" case.
"""
from __future__ import annotations
import logging
import logging.config
import pathlib

import pytest
from click.testing import CliRunner


def _drain_loggers(*names: str) -> None:
    """Flush + close handlers on the named loggers so the file contents
    are readable from the test process."""
    for name in names:
        for h in list(logging.getLogger(name).handlers):
            h.flush()
            h.close()


def test_build_log_config_writes_through_to_file(tmp_path, monkeypatch):
    """Wire the dictConfig and emit a message via each named app/uvicorn
    logger — all four should land in server.log. The sync.watch logger
    is asserted in its own test below to keep this one focused."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    from memorytalk.server import build_log_config

    server_log = tmp_path / "logs" / "server.log"
    watch_log = tmp_path / "logs" / "sync" / "watch.log"
    for p in (server_log, watch_log):
        p.parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(build_log_config(server_log, watch_log))
    try:
        logging.getLogger("memorytalk").info("app-message")
        logging.getLogger("uvicorn").info("uvicorn-message")
        logging.getLogger("uvicorn.error").info("uvicorn-error-message")
        logging.getLogger("uvicorn.access").info("uvicorn-access-message")
    finally:
        _drain_loggers("memorytalk", "uvicorn", "uvicorn.error", "uvicorn.access")

    content = server_log.read_text()
    assert "app-message" in content
    assert "uvicorn-message" in content
    assert "uvicorn-error-message" in content
    assert "uvicorn-access-message" in content


def test_sync_watch_log_isolated_from_server_log(tmp_path, monkeypatch):
    """``memorytalk.sync.watch`` writes to its own file and does NOT
    propagate up to ``memorytalk`` (which would duplicate every event
    into server.log)."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    from memorytalk.server import build_log_config

    server_log = tmp_path / "logs" / "server.log"
    watch_log = tmp_path / "logs" / "sync" / "watch.log"
    for p in (server_log, watch_log):
        p.parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(build_log_config(server_log, watch_log))
    try:
        logging.getLogger("memorytalk.sync.watch").info("watch-line")
    finally:
        _drain_loggers("memorytalk.sync.watch", "memorytalk")

    assert "watch-line" in watch_log.read_text()
    assert "watch-line" not in server_log.read_text(), (
        "sync.watch must not propagate into server.log — chatty watcher "
        "would crowd out app/request errors"
    )


def test_server_logs_command_no_file(tmp_path, monkeypatch):
    """Helpful message + nonzero exit when the log file doesn't exist."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    from memorytalk.cli.server import server_logs
    runner = CliRunner()
    result = runner.invoke(server_logs, [])
    assert result.exit_code == 1
    assert "no log file yet" in result.stderr or "no log file yet" in result.output


def test_server_logs_command_tails_last_n(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    body = "\n".join(f"line {i}" for i in range(1, 21))  # 20 lines
    (log_dir / "server.log").write_text(body)

    from memorytalk.cli.server import server_logs
    runner = CliRunner()
    result = runner.invoke(server_logs, ["-n", "5"])
    assert result.exit_code == 0, result.output
    # Last 5 lines only.
    assert "line 16" in result.output
    assert "line 20" in result.output
    assert "line 15" not in result.output


def test_logs_subcommand_registered():
    """`memory.talk server logs --help` is reachable from the top-level
    CLI (catches click decoration regressions)."""
    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["server", "logs", "--help"])
    assert result.exit_code == 0
    assert "Tail the daemon's log file" in result.output
