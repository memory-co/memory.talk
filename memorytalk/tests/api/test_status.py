"""GET /v4/status + CLI module-import smoke."""
from __future__ import annotations
import pytest


@pytest.mark.asyncio
async def test_status_running(client):
    r = await client.get("/v4/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["sessions_total"] == 0
    assert body["cards_total"] == 0
    assert body["insights_total"] == 0
    assert body["reviews_total"] == 0
    assert body["embedding_provider"] == "dummy"
    assert body["sync_enabled"] is False


@pytest.mark.asyncio
async def test_status_cards_vs_insights_split(app, client):
    """cards_total counts real v4 cards; insights_total counts legacy
    insights — they must not be conflated (issue #7)."""
    import datetime as _dt
    db = app.state.db
    now = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    # two legacy insights, no v4 cards
    for iid in ("insight_a", "insight_b"):
        await db.conn.execute(
            "INSERT INTO insights (card_id, insight, rounds, tags, created_at) "
            "VALUES (?, 'x', '[]', '{}', ?)", (iid, now))
    await db.conn.commit()
    r = await client.get("/v4/status")
    body = r.json()
    assert body["insights_total"] == 2
    assert body["cards_total"] == 0   # no v4 cards built yet

    # now create a real v4 card → cards_total moves, insights_total doesn't
    cr = await client.post("/v4/cards", json={"issue": "real card?"})
    cr.raise_for_status()
    body2 = (await client.get("/v4/status")).json()
    assert body2["cards_total"] == 1
    assert body2["insights_total"] == 2


def test_cli_main_imports():
    """Smoke: importing every CLI submodule and the main group succeeds.

    Equivalent to v2's ``test_cli_main_imports`` — catches missing modules
    or top-level syntax errors that would only otherwise show up when a
    user actually runs the command."""
    from memorytalk.cli import main  # registration walks all submodules
    # Force-instantiate each subcommand so click decorators run.
    cmd_names = list(main.commands.keys())
    assert {"server", "read", "setup", "sync", "search", "insight",
            "recall"}.issubset(set(cmd_names))
