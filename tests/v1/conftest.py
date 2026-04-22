"""Test fixtures — temp data root, API client."""
import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from memory_talk.api import create_app
from memory_talk.config import Config
from memory_talk.storage.init_db import init_db


def load_sessions_from_dir(dir_path: Path) -> list[Path]:
    """Return a list of Paths to .jsonl files in the given directory."""
    return sorted(dir_path.glob("*.jsonl"))


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
