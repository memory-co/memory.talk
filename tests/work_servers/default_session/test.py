"""work_servers/default_session -- scheme name as command. See README.md."""
from tests.conftest import needs_tmux

pytestmark = needs_tmux


def test_unknown_scheme_runs_as_a_command(client, home):
    w = client.post("/api/works", json={"goal": "x"}).json()
    d = client.post(f"/api/works/{w['id']}/sessions", json={"uri": f"sleep://{home / 'ws'}"})
    assert d.status_code == 201 and d.json()["scheme"] == "sleep" and d.json()["alive"]


def test_missing_command_is_400_and_leaves_no_session(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    r = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "nosuchcmd-zz://"})
    assert r.status_code == 400 and r.json()["error"] == "cmd_not_found"
    assert client.get(f"/api/works/{w['id']}/sessions").json() == []


def test_uri_without_scheme_is_400(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    r = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "no-scheme"})
    assert r.status_code == 400 and r.json()["error"] == "bad_uri"
