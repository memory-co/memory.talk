"""OpenAI-compatible embedding startup — validate_embedder hits DashScope.

Requires env var QWEN_KEY to be set to a valid DashScope API key. Without
it the test skips (the v2 startup check would raise EmbedderValidationError
and the CLI would return {status: failed}).
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import pytest


HERE = Path(__file__).parent


@pytest.mark.skipif(
    not os.environ.get("QWEN_KEY"),
    reason="QWEN_KEY env var not set — cannot validate DashScope embedding startup",
)
async def test_server_starts_with_openai_embedding(server_env):
    # Load the committed fixture and write it into the tmp data_root with the
    # random port merged in (ServerEnv.write_settings handles that).
    fixture_settings = json.loads((HERE / "settings.json").read_text(encoding="utf-8"))
    server_env.write_settings(fixture_settings)

    summary = server_env.start()
    assert summary["status"] == "started", (
        f"server failed to start with openai embedding: {summary}. "
        "This means validate_embedder() probing the DashScope endpoint failed. "
        "Check QWEN_KEY, network, or the endpoint URL."
    )

    status = server_env.wait_ready()
    assert status["status"] == "running"
    assert status["embedding_provider"] == "openai"

    stop_result = server_env.stop()
    assert stop_result["status"] == "stopped"
