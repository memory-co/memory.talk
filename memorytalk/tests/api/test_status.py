"""GET /v3/status + CLI module-import smoke."""
from __future__ import annotations
import pytest


@pytest.mark.asyncio
async def test_status_running(client):
    r = await client.get("/v3/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["sessions_total"] == 0
    assert body["cards_total"] == 0
    assert body["reviews_total"] == 0
    assert body["embedding_provider"] == "dummy"
    assert body["sync_enabled"] is False


def test_cli_main_imports():
    """Smoke: importing every CLI submodule and the main group succeeds.

    Equivalent to v2's ``test_cli_main_imports`` — catches missing modules
    or top-level syntax errors that would only otherwise show up when a
    user actually runs the command."""
    from memorytalk.cli import main  # registration walks all submodules
    # Force-instantiate each subcommand so click decorators run.
    cmd_names = list(main.commands.keys())
    assert {"server", "read", "setup", "sync", "search", "card",
            "review", "recall"}.issubset(set(cmd_names))
