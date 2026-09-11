"""work_servers/freeze -- done destroys presences, keeps records. See README.md."""
from tests.conftest import needs_tmux

pytestmark = needs_tmux


def test_done_destroys_sessions_but_keeps_registry(client, home):
    w = client.post("/api/works", json={"goal": "x"}).json()
    s = client.post(f"/api/works/{w['id']}/sessions", json={"uri": f"bash://{home / 'ws'}"}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "done"})
    sessions = client.get(f"/api/works/{w['id']}/sessions").json()
    assert [x["id"] for x in sessions] == [s["id"]] and sessions[0]["alive"] is False
    assert "frozen" in [e["type"] for e in client.get(f"/api/works/{w['id']}/events").json()]
