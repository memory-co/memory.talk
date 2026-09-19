"""works/canvas -- columns of sessions, optimistic lock. See README.md."""
from tests.conftest import needs_tmux

COLUMNS = [{"id": "c1", "panels": [{"session": "w-s1"}, {"session": "w-s2", "collapsed": True}]}, {"id": "c2", "panels": [], "collapsed": True}]


def test_fresh_canvas_is_empty_version_zero(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    assert client.get(f"/api/works/{w['id']}/canvas").json() == {"version": 0, "columns": []}


def test_put_bumps_version_and_keeps_order(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    cv = client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": COLUMNS}).json()
    assert cv["version"] == 1 and [(c["id"], c["collapsed"]) for c in cv["columns"]] == [("c1", False), ("c2", True)]
    assert [(p["session"], p["collapsed"]) for p in cv["columns"][0]["panels"]] == [("w-s1", False), ("w-s2", True)]


def test_stale_version_is_409(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": COLUMNS})
    assert client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": []}).status_code == 409


def test_duplicate_column_or_session_is_409(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    twice = [{"id": "c1", "panels": [{"session": "s"}]}, {"id": "c2", "panels": [{"session": "s"}]}]
    assert client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": twice}).status_code == 409
    same = [{"id": "c1", "panels": []}, {"id": "c1", "panels": []}]
    assert client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": same}).status_code == 409


def test_canvas_does_not_create_sessions(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": COLUMNS})
    assert client.get(f"/api/works/{w['id']}/sessions").json() == []


@needs_tmux
def test_new_session_lands_at_the_end_of_the_first_column(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    s1 = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "bash://"}).json()
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert cv["version"] == 1 and cv["columns"] == [{"id": "c1", "panels": [{"session": s1["id"], "collapsed": False}], "collapsed": False}]
    client.put(f"/api/works/{w['id']}/canvas", json={"version": 1, "columns": [{"id": "left", "panels": [{"session": s1["id"], "collapsed": True}]}, {"id": "right", "panels": []}]})
    s2 = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "bash://"}).json()
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert [p["session"] for p in cv["columns"][0]["panels"]] == [s1["id"], s2["id"]] and cv["columns"][0]["panels"][0]["collapsed"] is True


@needs_tmux
def test_detached_session_leaves_the_canvas(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    s1 = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "bash://"}).json()
    client.delete(f"/api/works/{w['id']}/sessions/{s1['id']}")
    assert client.get(f"/api/works/{w['id']}/canvas").json()["columns"] == [{"id": "c1", "panels": [], "collapsed": False}]
