"""End-to-end smoke test: real uvicorn subprocess + CLI → full write/read flow.

Skipped automatically if sockets/uvicorn setup is unavailable in the test
environment (e.g., no free port).
"""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def running_server(tmp_path):
    port = _free_port()
    data_root = tmp_path / ".memory-talk"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        json.dumps({
            "server": {"port": port},
            "embedding": {"provider": "dummy", "dim": 384},
        })
    )
    env = os.environ.copy()
    env["MEMORY_TALK_DATA_ROOT"] = str(data_root)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "memory_talk_v2.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    # Wait for the server to become ready
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 8.0
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base}/v2/status", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        proc.terminate()
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        pytest.skip(f"server did not become ready: {stderr}")

    yield base, data_root, proc

    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_full_write_read_flow_through_http(running_server):
    base, data_root, _ = running_server

    # Ingest a session
    r = httpx.post(f"{base}/v2/sessions", json={
        "session_id": "platform-e2e", "source": "claude-code",
        "created_at": "2026-04-22T00:00:00Z", "metadata": {"project": "e2e"},
        "sha256": "e2e-sha",
        "rounds": [
            {"round_id": "r1", "parent_id": None, "timestamp": "",
             "speaker": "user", "role": "human",
             "content": [{"type": "text", "text": "选定 LanceDB 做向量存储"}],
             "is_sidechain": False},
            {"round_id": "r2", "parent_id": "r1", "timestamp": "",
             "speaker": "assistant", "role": "assistant",
             "content": [{"type": "text", "text": "零依赖、嵌入式"}],
             "is_sidechain": False},
        ],
    }, timeout=10.0)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]

    # Create a card
    r = httpx.post(f"{base}/v2/cards", json={
        "summary": "选定 LanceDB 做向量存储",
        "rounds": [{"session_id": sid, "indexes": "1-2"}],
    }, timeout=10.0)
    assert r.status_code == 200, r.text
    card_id = r.json()["card_id"]

    # Search
    r = httpx.post(f"{base}/v2/search", json={"query": "LanceDB"}, timeout=15.0)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cards"]["count"] >= 1
    # Snippet mentions LanceDB highlighted
    assert any("**" in s for s in data["cards"]["results"][0]["snippets"])

    # View the card
    r = httpx.post(f"{base}/v2/view", json={"id": card_id}, timeout=10.0)
    assert r.status_code == 200
    assert r.json()["card"]["card_id"] == card_id

    # Log for session includes imported + card_extracted
    r = httpx.post(f"{base}/v2/log", json={"id": sid}, timeout=10.0)
    kinds = [e["kind"] for e in r.json()["events"]]
    assert "imported" in kinds and "card_extracted" in kinds

    # Status shows counts
    r = httpx.get(f"{base}/v2/status", timeout=5.0).json()
    assert r["sessions_total"] == 1 and r["cards_total"] == 1
    assert r["searches_total"] >= 1

    # Rebuild — confirm full replay works over HTTP
    r = httpx.post(f"{base}/v2/rebuild", json={}, timeout=30.0)
    assert r.status_code == 200
    assert r.json()["cards"] == 1 and r.json()["sessions"] == 1
