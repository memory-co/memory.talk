"""Shared fixture for `memory-talk server {start,stop,status}` scenarios.

These tests exercise the REAL CLI against a REAL uvicorn subprocess (on a
random free port, not 7788) — unlike tests/cli/sync/ which routes httpx
through ASGITransport to avoid spawning a server. Server lifecycle is the
whole point here, so we can't short-circuit.

Each test gets a fresh tmp data_root + free port + CliRunner. Cleanup
always tries `server stop` even if the test body raised, so stray uvicorn
processes don't linger.
"""
from __future__ import annotations
import json
import socket
import time
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from memorytalk.cli import main


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ServerEnv:
    def __init__(self, data_root: Path, port: int, runner: CliRunner):
        self.data_root = data_root
        self.port = port
        self.runner = runner

    def write_settings(self, settings: dict) -> None:
        """Write settings.json with the random port injected under `server.port`."""
        merged = {**settings, "server": {"port": self.port}}
        (self.data_root / "settings.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2)
        )

    def start(self) -> dict:
        r = self.runner.invoke(main, ["server", "start", "--data-root", str(self.data_root),
        "--json",
    ])
        if not r.stdout.strip():
            raise RuntimeError(
                f"`server start` produced no stdout. exit_code={r.exit_code}. "
                f"stderr={r.stderr!r}"
            )
        return json.loads(r.stdout)

    def stop(self) -> dict:
        r = self.runner.invoke(main, ["server", "stop", "--data-root", str(self.data_root),
        "--json",
    ])
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def wait_ready(self, timeout: float = 10.0) -> dict:
        """Poll GET /v2/status until it responds 200, or time out."""
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{self.port}/v2/status", timeout=2.0)
                if r.status_code == 200:
                    return r.json()
            except Exception as e:
                last_err = e
            time.sleep(0.2)
        raise RuntimeError(f"server never became ready on :{self.port}; last error: {last_err}")


@pytest.fixture
def server_env(tmp_path):
    data_root = tmp_path / ".mt"
    data_root.mkdir()
    env = ServerEnv(data_root=data_root, port=_free_port(), runner=CliRunner())
    try:
        yield env
    finally:
        # Always attempt to tear the server down, even if the test raised
        # mid-way. Ignore any errors — a stray pid is better than a
        # follow-up exception that masks the real failure.
        try:
            env.stop()
        except Exception:
            pass
