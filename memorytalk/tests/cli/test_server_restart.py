"""restart_server_proc + ``server restart`` CLI.

Skips an actual subprocess fork — that's heavyweight + flaky in a test
suite. Instead we mock the lifecycle primitives (``start_server_proc``,
``pid_alive``, ``os.kill``, ``time.sleep``) and assert the orchestration:
no-previous → start; previous alive → SIGTERM + wait + start; previous
ignores SIGTERM → SIGKILL escalation; start failure carries previous_pid.
"""
from __future__ import annotations
import signal

import pytest
from click.testing import CliRunner


# ────────── CLI help shape ──────────

def test_server_restart_help():
    from memorytalk.cli import main
    r = CliRunner().invoke(main, ["server", "restart", "--help"])
    assert r.exit_code == 0, r.output
    assert "restart" in r.output.lower()


def test_server_group_lists_restart():
    from memorytalk.cli import main
    r = CliRunner().invoke(main, ["server", "--help"])
    assert r.exit_code == 0
    assert "restart" in r.output


# ────────── restart_server_proc behavior ──────────

def _make_cfg(tmp_path, *, pid_text: str | None = None):
    """Build a minimal Config-shaped object with pid/port file paths
    under ``tmp_path`` so each test starts from a known state."""
    pid_path = tmp_path / "server.pid"
    port_path = tmp_path / "server.port"
    if pid_text is not None:
        pid_path.write_text(pid_text)
    from types import SimpleNamespace
    return SimpleNamespace(pid_path=pid_path, port_path=port_path)


def test_restart_no_previous_degenerates_to_start(tmp_path, monkeypatch):
    """No pid file → restart should just start fresh, return ``started``
    status (NOT ``restarted``) so users can tell the daemon was newly
    spawned vs. replacing something."""
    from memorytalk.cli import server as srv
    cfg = _make_cfg(tmp_path)  # no pid file

    monkeypatch.setattr(srv, "start_server_proc", lambda c: {
        "status": "started", "pid": 4321, "port": 7788,
    })
    payload = srv.restart_server_proc(cfg)
    assert payload == {"status": "started", "pid": 4321, "port": 7788}


def test_restart_stale_pid_file_treated_as_no_previous(tmp_path, monkeypatch):
    """Pid file exists but contains junk → treat as no previous daemon."""
    from memorytalk.cli import server as srv
    cfg = _make_cfg(tmp_path, pid_text="not-an-int")

    monkeypatch.setattr(srv, "start_server_proc", lambda c: {
        "status": "started", "pid": 9999, "port": 7788,
    })
    payload = srv.restart_server_proc(cfg)
    assert payload["status"] == "started"  # not "restarted"


def test_restart_previous_alive_sends_sigterm_then_starts(tmp_path, monkeypatch):
    """Previous daemon alive → SIGTERM, wait for exit, then start. The
    final payload distinguishes itself from a plain ``start`` by
    carrying ``previous_pid``."""
    from memorytalk.cli import server as srv
    cfg = _make_cfg(tmp_path, pid_text="12345")

    # pid_alive returns True once (initial check), then False (post-SIGTERM).
    alive_calls = iter([True, False])
    monkeypatch.setattr(srv, "pid_alive", lambda pid: next(alive_calls, False))

    killed = []
    monkeypatch.setattr(srv.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    monkeypatch.setattr(srv, "start_server_proc", lambda c: {
        "status": "started", "pid": 99999, "port": 7788,
    })

    payload = srv.restart_server_proc(cfg)
    assert payload == {
        "status": "restarted",
        "previous_pid": 12345,
        "pid": 99999,
        "port": 7788,
    }
    # Exactly one SIGTERM, no SIGKILL (graceful exit observed).
    assert (12345, signal.SIGTERM) in killed
    assert (12345, signal.SIGKILL) not in killed


def test_restart_escalates_to_sigkill_after_grace_period(tmp_path, monkeypatch):
    """Previous daemon doesn't respond to SIGTERM in the grace window
    → SIGKILL fallback. The user gets a working restart instead of a
    CLI hang."""
    from memorytalk.cli import server as srv
    cfg = _make_cfg(tmp_path, pid_text="12345")

    # pid_alive always returns True during the poll loop → forces the
    # else branch of while/else, which sends SIGKILL.
    monkeypatch.setattr(srv, "pid_alive", lambda pid: True)

    # Make the grace window collapse so the polling loop exits quickly.
    monkeypatch.setattr(srv, "_RESTART_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(srv, "_RESTART_POLL_INTERVAL", 0.01)

    killed = []
    monkeypatch.setattr(srv.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    monkeypatch.setattr(srv, "start_server_proc", lambda c: {
        "status": "started", "pid": 7000, "port": 7788,
    })

    payload = srv.restart_server_proc(cfg)
    assert payload["status"] == "restarted"
    assert payload["previous_pid"] == 12345
    # Both signals were sent: SIGTERM first, SIGKILL after grace.
    sent = [sig for (_pid, sig) in killed]
    assert signal.SIGTERM in sent
    assert signal.SIGKILL in sent


def test_restart_start_failure_carries_previous_pid(tmp_path, monkeypatch):
    """If the new daemon fails to start, the payload must surface
    ``previous_pid`` so operators know the old daemon is *already gone*
    — they don't get a misleading "daemon still up" mental model."""
    from memorytalk.cli import server as srv
    cfg = _make_cfg(tmp_path, pid_text="12345")

    monkeypatch.setattr(srv, "pid_alive", lambda pid: False)  # already dead
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    monkeypatch.setattr(srv, "start_server_proc", lambda c: {
        "status": "failed", "exit_code": 1, "error": "port in use",
    })

    payload = srv.restart_server_proc(cfg)
    assert payload["status"] == "failed"
    assert payload["previous_pid"] == 12345
    assert payload["exit_code"] == 1


# ────────── formatter shape ──────────

def test_fmt_server_restart_restarted():
    from memorytalk.cli._format import fmt_server_restart
    out = fmt_server_restart({
        "status": "restarted", "previous_pid": 100,
        "pid": 200, "port": 7788,
    })
    assert "restarted" in out
    assert "100" in out
    assert "200" in out
    assert "7788" in out


def test_fmt_server_restart_started_when_no_previous():
    from memorytalk.cli._format import fmt_server_restart
    out = fmt_server_restart({
        "status": "started", "pid": 200, "port": 7788,
    })
    assert "started" in out
    assert "was not running" in out


def test_fmt_server_restart_failed_reuses_start_format():
    from memorytalk.cli._format import fmt_server_restart
    out = fmt_server_restart({
        "status": "failed", "exit_code": 1, "error": "port in use",
    })
    assert "error" in out.lower()
    assert "port in use" in out
