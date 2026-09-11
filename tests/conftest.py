import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(params=["fs", "sqlite"])
def home(tmp_path, monkeypatch, request):
    monkeypatch.setenv("MEMORY_TALK_STORE", request.param)
    monkeypatch.setenv("MEMORY_TALK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_TALK_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("MEMORY_TALK_CLAUDE_PROJECTS", str(tmp_path / "claude"))
    monkeypatch.setenv("MEMORY_TALK_CODEX_SESSIONS", str(tmp_path / "codex"))
    monkeypatch.setenv("MEMORY_TALK_KIMI_SESSIONS", str(tmp_path / "kimi"))
    monkeypatch.setenv("MEMORY_TALK_TMUX_SOCKET", f"mt-test-{uuid.uuid4().hex[:8]}")
    monkeypatch.delenv("MEMORY_TALK_TTYD_URL", raising=False)
    yield tmp_path
    subprocess.run(["tmux", "-L", os.environ["MEMORY_TALK_TMUX_SOCKET"], "kill-server"],
                   capture_output=True)


@pytest.fixture
def client(home):
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    app = create_app(load_config(), load_runtime_config())
    with TestClient(app) as c:
        for name in ("alice", "bob", "carol"):          # 场景里用到的 user 先注册
            c.post("/api/users", json={"name": name})
        yield c
