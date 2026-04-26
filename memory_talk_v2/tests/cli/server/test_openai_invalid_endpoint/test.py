"""Server startup with a key but an unreachable OpenAI endpoint must fail."""
from __future__ import annotations
import socket

import pytest


def _grab_free_port() -> int:
    """Pick a port that's free RIGHT NOW. We don't bind it; OS will reissue —
    but the window is microscopic and the embedding probe just needs a place
    that refuses connections."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def test_server_fails_to_start_with_invalid_endpoint(server_env, monkeypatch):
    monkeypatch.setenv("FAKE_EMB_KEY", "sk-fake-but-present")
    bogus_port = _grab_free_port()
    server_env.write_settings({
        "embedding": {
            "provider": "openai",
            "endpoint": f"http://127.0.0.1:{bogus_port}/v1/embeddings",
            "auth_env_key": "FAKE_EMB_KEY",
            "model": "ignored",
            "dim": 1024,
            "timeout": 3.0,
        },
    })

    summary = server_env.start()
    if summary["status"] == "failed":
        # Subprocess died inside the parent's 1.2s peek window — common path.
        assert "embedding" in summary["error"].lower()
    else:
        # Parent's peek window raced the subprocess death; the worker is
        # either dying or already gone, but `start` wrote the pid anyway.
        # Confirm the contract via /v2/status — it must never come up.
        assert summary["status"] == "started"
        with pytest.raises(RuntimeError, match="never became ready"):
            server_env.wait_ready(timeout=3.0)
