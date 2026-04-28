"""Default-config startup: no settings beyond port → dummy embedder, no network."""
from __future__ import annotations


async def test_server_starts_with_default_settings(server_env):
    # Only override port; everything else uses defaults (embedding: dummy).
    server_env.write_settings({})

    summary = server_env.start()
    assert summary["status"] == "started", f"unexpected start result: {summary}"
    assert summary["port"] == server_env.port
    assert isinstance(summary["pid"], int) and summary["pid"] > 0

    status = server_env.wait_ready()
    assert status["status"] == "running"
    assert status["embedding_provider"] == "dummy"
    assert status["vector_provider"] == "lancedb"
    assert status["relation_provider"] == "sqlite"
    assert status["data_root"] == str(server_env.data_root)

    # Counts — empty data root, nothing ingested
    assert status["sessions_total"] == 0
    assert status["cards_total"] == 0
    assert status["links_total"] == 0
    assert status["searches_total"] == 0

    stop_result = server_env.stop()
    assert stop_result["status"] == "stopped"
