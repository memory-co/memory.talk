import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_HOME", str(tmp_path / "home"))
    from config import load_config
    from main import create_app
    app = create_app(load_config())
    with TestClient(app) as c:
        yield c
