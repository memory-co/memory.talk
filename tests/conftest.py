"""Test fixtures — temp data root, API client, fake sessions."""
import json
import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from memory_talk.api import create_app
from memory_talk.config import Config
from memory_talk.storage.init_db import init_db

@pytest.fixture
def temp_root():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture
def config(temp_root):
    c = Config(temp_root)
    c.ensure_dirs()
    c.save()
    init_db(c.db_path)
    return c

@pytest.fixture
def client(config):
    app = create_app(config)
    with TestClient(app) as c:
        yield c

@pytest.fixture
def fake_claude_sessions(temp_root):
    projects = temp_root / "claude_projects" / "testproject"
    projects.mkdir(parents=True)

    # Session 1: database decision
    s1 = projects / "sess_db_decision.jsonl"
    lines = [
        json.dumps({"type": "user", "uuid": "u001", "parentUuid": None, "timestamp": "2026-04-10T10:00:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "我们需要一个向量数据库，ChromaDB 和 LanceDB 你怎么看？"}}),
        json.dumps({"type": "assistant", "uuid": "a001", "parentUuid": "u001", "timestamp": "2026-04-10T10:00:05Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "关键考量是部署形态"}, {"type": "text", "text": "ChromaDB 功能成熟但需要独立服务进程。LanceDB 是嵌入式方案，零依赖。"}]}}),
        json.dumps({"type": "user", "uuid": "u002", "parentUuid": "a001", "timestamp": "2026-04-10T10:01:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "就用 LanceDB，零依赖这点太重要了。"}}),
    ]
    s1.write_text("\n".join(lines) + "\n")

    # Session 2: bug investigation
    s2 = projects / "sess_bug_investigation.jsonl"
    lines = [
        json.dumps({"type": "user", "uuid": "b001", "parentUuid": None, "timestamp": "2026-04-11T09:00:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "memory-talk cards create 有时候会卡住"}}),
        json.dumps({"type": "assistant", "uuid": "b002", "parentUuid": "b001", "timestamp": "2026-04-11T09:00:05Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "卡住不是报错是阻塞"}, {"type": "text", "text": "卡在 _ensure_table 方法"}]}}),
        json.dumps({"type": "assistant", "uuid": "b003", "parentUuid": "b002", "timestamp": "2026-04-11T09:05:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "text", "text": "LanceDB create_table 在 NFS 上会触发 fsync"}]}}),
        json.dumps({"type": "user", "uuid": "b004", "parentUuid": "b003", "timestamp": "2026-04-11T09:05:30Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "user", "content": "我确实是在 NFS 上跑的"}}),
        json.dumps({"type": "assistant", "uuid": "b005", "parentUuid": "b004", "timestamp": "2026-04-11T09:06:00Z", "isSidechain": False, "cwd": "/home/user/myapp", "message": {"role": "assistant", "content": [{"type": "text", "text": "修复方案：预创建表结构"}]}}),
    ]
    s2.write_text("\n".join(lines) + "\n")

    return projects
