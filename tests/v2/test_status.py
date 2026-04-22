from fastapi.testclient import TestClient
from memory_talk.api import create_app
from memory_talk.config import Config


def test_v2_status_running(tmp_path):
    (tmp_path / "settings.json").write_text('{"embedding": {"provider": "dummy"}}')
    cfg = Config(str(tmp_path))
    app = create_app(cfg)
    client = TestClient(app)

    resp = client.get("/v2/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert "sessions_total" in data
    assert "cards_total" in data
    assert "links_total" in data
    assert "searches_total" in data
    assert data["data_root"] == str(tmp_path)
    assert data["embedding_provider"] == "dummy"
