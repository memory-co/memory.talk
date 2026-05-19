"""Tests for the daemon log pipeline.

We don't spawn the real daemon here — these tests exercise the pieces
in isolation:

- ``build_log_config`` + ``dictConfig`` actually wires the
  ``memorytalk``/``uvicorn`` loggers to a rotating file handler.
- ``memory-talk server logs`` reads from the configured path and
  handles the "no log yet" case.
"""
from __future__ import annotations
import logging
import logging.config
import pathlib

import pytest
from click.testing import CliRunner


def test_build_log_config_writes_through_to_file(tmp_path, monkeypatch):
    """Wire the dictConfig and emit a message via each named logger —
    all four should land in the file."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    from memorytalk.server import build_log_config

    log_path = tmp_path / "logs" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(build_log_config(log_path))
    try:
        logging.getLogger("memorytalk").info("app-message")
        logging.getLogger("uvicorn").info("uvicorn-message")
        logging.getLogger("uvicorn.error").info("uvicorn-error-message")
        logging.getLogger("uvicorn.access").info("uvicorn-access-message")
    finally:
        # Flush so the file is readable. Closing the handler also
        # releases the file lock on Windows.
        for h in list(logging.getLogger("memorytalk").handlers):
            h.flush()
            h.close()

    content = log_path.read_text()
    assert "app-message" in content
    assert "uvicorn-message" in content
    assert "uvicorn-error-message" in content
    assert "uvicorn-access-message" in content


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
    """`memory-talk server logs --help` is reachable from the top-level
    CLI (catches click decoration regressions)."""
    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["server", "logs", "--help"])
    assert result.exit_code == 0
    assert "Tail the daemon's log file" in result.output
