"""Pure-FTS mode: probes target the sessions bucket (FTS-only by design).

Both modes use the SAME real OpenAI-compatible embedding (DashScope/Qwen).
Differences:
- This tree's probes target ``sess_<label>`` ids.
- Cards' embedding API calls still happen (the search endpoint embeds the
  query for the cards bucket regardless), but those results are ignored
  since probes only look at the sessions bucket. As the trees diverge,
  they may pick different probe targets per case.

Fixture flow (package-scoped — corpus seeded ONCE for all 4 cases here):
1. Copy committed file-layer corpus (`tests/search/corpus/{sessions,cards}/`)
   into a tmp data root.
2. Write QWEN-backed `settings.json`.
3. Start the app — lifespan validates the embedding endpoint (FAILS if
   QWEN_KEY is missing, by design).
4. POST `/v2/rebuild` to populate SQLite + LanceDB + FTS index from the
   on-disk truth (this is where embeddings get computed).

Subsequent tests just hit `/v2/search`.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memory_talk_v2.api import create_app
from memory_talk_v2.config import Config


CORPUS_ROOT = Path(__file__).parent.parent / "corpus"


@pytest.fixture(scope="package")
def data_root(tmp_path_factory):
    d = tmp_path_factory.mktemp("search_pure_fts") / ".memory-talk"
    d.mkdir(parents=True, exist_ok=True)
    # Copy the committed file-layer corpus into the tmp data root.
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
        # Populate SQLite + LanceDB + FTS from the file-layer truth.
        r = client.post("/v2/rebuild", json={})
        assert r.status_code == 200, f"rebuild failed: {r.status_code} {r.text}"
        body = r.json()
        assert body["status"] == "ok", body
        yield client
