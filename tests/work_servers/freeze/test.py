"""work_servers/freeze -- done destroys presences, keeps records. See README.md."""
from tests.conftest import needs_tmux

pytestmark = needs_tmux


def test_done_destroys_sessions_but_keeps_registry(client, home):
    w = client.post("/api/works", json={"goal": "x"}).json()
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "done"})
    worklets = client.get(f"/api/works/{w['id']}/worklets").json()
    assert [x["id"] for x in worklets] == [s["id"]] and worklets[0]["alive"] is False
    assert "frozen" in [e["type"] for e in client.get(f"/api/works/{w['id']}/events").json()]
