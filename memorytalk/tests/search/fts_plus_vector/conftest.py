"""FTS + vector hybrid mode: probes target the cards bucket (RRF FTS+vector).

Same OpenAI-compatible embedding (DashScope/Qwen) as the sister tree —
QWEN_KEY is required, missing key fails (no skip), matching the policy
of `tests/cli/server/test_openai_embedding_start/`.

Fixture flow (package-scoped — corpus seeded ONCE for all 4 cases here):
1. Copy committed file-layer corpus (`tests/search/corpus/{sessions,cards}/`)
   into a tmp data root.
2. Write QWEN-backed `settings.json`.
3. Start the app — lifespan validates the embedding endpoint.
4. POST `/v2/rebuild` to populate SQLite + LanceDB + FTS from on-disk truth.
   Card embeddings are computed here against the real DashScope endpoint.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memorytalk.api import create_app
from memorytalk.config import Config


CORPUS_ROOT = Path(__file__).parent.parent / "corpus"


@pytest.fixture(scope="package")
def data_root(tmp_path_factory):
    d = tmp_path_factory.mktemp("search_fts_plus_vector") / ".memory-talk"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CORPUS_ROOT / "sessions", d / "sessions")
    shutil.copytree(CORPUS_ROOT / "cards", d / "cards")
    (d / "settings.json").write_text(json.dumps({
        "embedding": {
            "provider": "openai",
            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            "auth_env_key": "QWEN_KEY",
            "model": "text-embedding-v4",
            "dim": 1024,
        },
        "ttl": {
            "card": {"initial": 3600, "factor": 2.0, "max": 86400},
            "link": {"initial": 1800, "factor": 2.0, "max": 43200},
        },
    }))
    return d


@pytest.fixture(scope="package")
def app_client(data_root: Path):
    cfg = Config(data_root)
    app = create_app(cfg)
    with TestClient(app) as client:
        r = client.post("/v2/rebuild", json={})
        assert r.status_code == 200, f"rebuild failed: {r.status_code} {r.text}"
        body = r.json()
        assert body["status"] == "ok", body
        yield client
