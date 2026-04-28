"""OpenAI-compatible embedding startup — validate_embedder hits DashScope.

Requires env var QWEN_KEY to be set to a valid DashScope API key. Without
it the test FAILS (not skips): a production server would refuse to start
with this settings.json and that failure is exactly what we want the test
to surface.
"""
from __future__ import annotations
import json
from pathlib import Path


HERE = Path(__file__).parent


async def test_server_starts_with_openai_embedding(server_env):
    # Load the committed fixture and write it into the tmp data_root with the
    # random port merged in (ServerEnv.write_settings handles that).
    fixture_settings = json.loads((HERE / "settings.json").read_text(encoding="utf-8"))
    server_env.write_settings(fixture_settings)

    summary = server_env.start()
    assert summary["status"] == "started", (
        f"server failed to start with openai embedding: {summary}. "
        "Check that QWEN_KEY is set to a valid DashScope key, the endpoint "
        "is reachable, and the configured dim (1024) matches the model."
    )

    status = server_env.wait_ready()
    assert status["status"] == "running"
    assert status["embedding_provider"] == "openai"

    stop_result = server_env.stop()
    assert stop_result["status"] == "stopped"
