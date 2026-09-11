import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_orig_json = httpx.Response.json


def _unwrap(self, **kw):
    """API 响应是 {data, message[, error]} 信封:成功时 .json() 直接给 data,出错时给整个信封(测试看 error 码)。"""
    body = _orig_json(self, **kw)
    if isinstance(body, dict) and "data" in body and "message" in body and "error" not in body:
        return body["data"]
    return body


httpx.Response.json = _unwrap

needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="需要 tmux")


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
    subprocess.run(["tmux", "-L", os.environ["MEMORY_TALK_TMUX_SOCKET"], "kill-server"], capture_output=True)


@pytest.fixture
def client(home):
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    app = create_app(load_config(), load_runtime_config())
    with TestClient(app) as c:
        for name in ("alice", "bob", "carol"):
            c.post("/api/users", json={"name": name})
        yield c


@pytest.fixture
def svc(client):
    return client.app.state


@pytest.fixture
def H():
    return lambda user: {"X-Memory-Talk-User": user}


# ---- 各场景共用的小工具 ----

def git_log(client, ref="stack", n=50) -> str:
    """collections 仓库的提交历史;stack 用 first-parent(每个 merge 节点 = 一次层提交)。"""
    root = client.app.state.collections.repo.root
    args = ["git", "-c", "core.quotepath=false", "log", f"-{n}", "--format=%s%n%b"] + (["--first-parent"] if ref == "stack" else []) + [ref]
    return subprocess.run(args, cwd=root, capture_output=True, text=True).stdout


def git_authors(client, n=5) -> list[str]:
    root = client.app.state.collections.repo.root
    return subprocess.run(["git", "log", f"-{n}", "--first-parent", "--format=%an <%ae>", "stack"], cwd=root,
                          capture_output=True, text=True).stdout.split()
