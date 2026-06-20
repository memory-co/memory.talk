"""start_server_proc polls /v4/status for real readiness instead of a
fixed 1.2s liveness window — so a daemon that crashes mid-startup (e.g.
the v3→v4 migration exiting at ~2s) is reported ``failed``, not
``started`` with a stale pid. See issue #6.

We mock the subprocess + the HTTP probe rather than spawning uvicorn.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _make_cfg(tmp_path):
    """Minimal Config-shaped object: pid/port file paths + logs_dir + the
    bits start_server_proc touches."""
    logs = tmp_path / "logs"
    logs.mkdir()
    return SimpleNamespace(
        pid_path=tmp_path / "server.pid",
        port_path=tmp_path / "server.port",
        logs_dir=logs,
        data_root=tmp_path,
        ensure_dirs=lambda: None,
        settings=SimpleNamespace(server=SimpleNamespace(port=7788)),
    )


class _FakeProc:
    def __init__(self, pid=4321, poll_seq=None, stderr=b""):
        self.pid = pid
        self.returncode = None
        # poll() returns each value from poll_seq in turn (None=alive).
        self._poll_seq = list(poll_seq or [None])
        self.stderr = SimpleNamespace(read=lambda: stderr)

    def poll(self):
        if not self._poll_seq:
            return self.returncode
        val = self._poll_seq.pop(0)
        if val is not None:
            self.returncode = val
        return val


@pytest.fixture
def patch_env(tmp_path, monkeypatch):
    from memorytalk.cli import server as srv

    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    # Drop the readiness budget so a "never ready" run doesn't take 15s.
    monkeypatch.setattr(srv, "_START_READY_SECONDS", 0.5)
    monkeypatch.setattr(srv, "_START_POLL_INTERVAL", 0.0)
    return srv


def test_daemon_comes_up_returns_started(patch_env, tmp_path, monkeypatch):
    srv = patch_env
    cfg = _make_cfg(tmp_path)

    proc = _FakeProc(pid=4321, poll_seq=[None, None])
    monkeypatch.setattr(srv.subprocess, "Popen", lambda *a, **k: proc)
    # Probe fails once (still booting), then 200.
    responses = iter([False, True])
    monkeypatch.setattr(srv, "_server_responsive", lambda c: next(responses, True))

    payload = srv.start_server_proc(cfg)

    assert payload["status"] == "started"
    assert payload["pid"] == 4321
    assert payload["port"] == 7788
    assert cfg.pid_path.read_text() == "4321"
    assert cfg.port_path.read_text() == "7788"


def test_daemon_dies_during_startup_returns_failed(patch_env, tmp_path, monkeypatch):
    """Process exits (SystemExit(3)) before ever answering /status → the
    old code reported ``started``; now it must be ``failed`` with NO pid
    file written."""
    srv = patch_env
    cfg = _make_cfg(tmp_path)

    proc = _FakeProc(pid=999, poll_seq=[3], stderr=b"migration boom")
    monkeypatch.setattr(srv.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(srv, "_server_responsive", lambda c: False)

    payload = srv.start_server_proc(cfg)

    assert payload["status"] == "failed"
    assert payload["exit_code"] == 3
    assert "boom" in payload["error"]
    assert not cfg.pid_path.exists()        # no stale pid
    assert not cfg.port_path.exists()       # cleaned up


def test_daemon_never_ready_times_out_to_failed(patch_env, tmp_path, monkeypatch):
    """Process stays alive but /status never returns 200 → ``failed`` on
    timeout, no pid written."""
    srv = patch_env
    cfg = _make_cfg(tmp_path)

    proc = _FakeProc(pid=555, poll_seq=[None])  # always alive
    monkeypatch.setattr(srv.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(srv, "_server_responsive", lambda c: False)

    payload = srv.start_server_proc(cfg)

    assert payload["status"] == "failed"
    assert not cfg.pid_path.exists()
    assert not cfg.port_path.exists()
    assert payload["error"]  # a hint is surfaced
