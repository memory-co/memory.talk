def test_v2_status_ok(app_client, tmp_data_root):
    resp = app_client.get("/v2/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["embedding_provider"] == "dummy"
    assert data["vector_provider"] == "lancedb"
    assert data["data_root"] == str(tmp_data_root)
    assert data["sessions_total"] == 0
    assert data["cards_total"] == 0
    assert data["links_total"] == 0
    assert data["searches_total"] == 0


def test_cli_main_imports():
    from memory_talk_v2.cli import main
    assert main is not None
