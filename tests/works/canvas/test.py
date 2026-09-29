"""works/canvas -- columns (fixed number + alias) of worklets, one request per action. See README.md."""
from tests.conftest import needs_tmux


def _work(client):
    return client.post("/api/works", json={"goal": "x"}).json()


def _events(client, w, prefix=""):
    return [e for e in client.get(f"/api/works/{w['id']}/events").json() if e["type"].startswith(prefix)]


def test_fresh_canvas_has_one_column_c1(client):
    w = _work(client)
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert cv["version"] == 0 and cv["next_column"] == 2
    assert cv["columns"] == [{"id": "c1", "alias": "", "panels": [], "collapsed": False}]


def test_add_column_numbers_are_monotonic_and_never_reused(client):
    w = _work(client)
    base = f"/api/works/{w['id']}/columns"
    assert [c["id"] for c in client.post(base, json={}).json()["columns"]] == ["c1", "c2"]
    client.delete(f"{base}/c2")
    cv = client.post(base, json={"alias": "调研", "beside": "c1", "side": "left"}).json()
    assert [(c["id"], c["alias"]) for c in cv["columns"]] == [("c3", "调研"), ("c1", "")]      # c2 删了也不再发
    assert cv["version"] == 3 and cv["next_column"] == 4


def test_rename_only_changes_the_alias_and_is_an_event(client, H):
    w = _work(client)
    cv = client.patch(f"/api/works/{w['id']}/columns/c1", json={"alias": " 测试 "}, headers=H("alice")).json()
    assert cv["columns"][0] == {"id": "c1", "alias": "测试", "panels": [], "collapsed": False}
    [e] = _events(client, w, "column.")
    assert e["type"] == "column.renamed" and e["data"] == {"by": "alice", "column": {"id": "c1", "alias": "测试"}, "from": ""}


def test_collapse_column_is_not_an_event(client):
    w = _work(client)
    assert client.patch(f"/api/works/{w['id']}/columns/c1", json={"collapsed": True}).json()["columns"][0]["collapsed"] is True
    assert _events(client, w, "column.") == []


def test_add_and_remove_column_are_events(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "右"})
    client.delete(f"/api/works/{w['id']}/columns/c2")
    assert [(e["type"], e["data"]["column"]) for e in _events(client, w, "column.")] == \
        [("column.added", {"id": "c2", "alias": "右"}), ("column.removed", {"id": "c2", "alias": "右"})]


def test_last_column_cannot_be_removed(client):
    w = _work(client)
    assert client.delete(f"/api/works/{w['id']}/columns/c1").status_code == 409


def test_unknown_column_is_404(client):
    w = _work(client)
    assert client.patch(f"/api/works/{w['id']}/columns/c9", json={"alias": "x"}).status_code == 404
    assert client.post(f"/api/works/{w['id']}/columns", json={"beside": "c9"}).status_code == 404
    assert client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c9"}).status_code == 404


def test_put_canvas_is_gone(client):
    w = _work(client)
    assert client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": []}).status_code == 405


def test_legacy_canvas_is_normalized_on_read(client, svc):
    w = _work(client)
    svc.works.repo.put_doc(w["id"], "canvas", {"version": 4, "columns": [
        {"id": "left", "name": "旧名", "panels": []}, {"id": "c2", "panels": []}, {"id": "right", "panels": []}]})
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert [(c["id"], c["alias"]) for c in cv["columns"]] == [("c3", "旧名"), ("c2", ""), ("c4", "")]
    assert cv["version"] == 4 and cv["next_column"] == 5


@needs_tmux
def test_attach_lands_in_the_given_column_and_the_event_says_so(client, H):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "测试"})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c2"}, headers=H("alice")).json()
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert [[p["worklet"] for p in c["panels"]] for c in cv["columns"]] == [[], [s["id"]]]
    [e] = _events(client, w, "worklet.attached")
    assert e["data"]["by"] == "alice" and e["data"]["column"] == {"id": "c2", "alias": "测试"}


@needs_tmux
def test_attach_without_column_goes_to_the_leftmost(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"beside": "c1", "side": "left"})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert cv["columns"][0]["id"] == "c2" and [p["worklet"] for p in cv["columns"][0]["panels"]] == [s["id"]]


@needs_tmux
def test_move_between_and_within_columns(client, H):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "右"})
    s1 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    s2 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    cv = client.post(f"/api/works/{w['id']}/worklets/{s1['id']}/move", json={"column": "c2"}, headers=H("bob")).json()
    assert [[p["worklet"] for p in c["panels"]] for c in cv["columns"]] == [[s2["id"]], [s1["id"]]]
    cv = client.post(f"/api/works/{w['id']}/worklets/{s1['id']}/move", json={"column": "c1", "index": 0}).json()
    assert [p["worklet"] for p in cv["columns"][0]["panels"]] == [s1["id"], s2["id"]]
    first = _events(client, w, "worklet.moved")[0]["data"]
    assert first["by"] == "bob" and first["from"] == {"column": {"id": "c1", "alias": ""}, "index": 0} \
        and first["to"] == {"column": {"id": "c2", "alias": "右"}, "index": 0}


@needs_tmux
def test_collapse_worklet_is_not_an_event(client):
    w = _work(client)
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    cv = client.patch(f"/api/works/{w['id']}/worklets/{s['id']}", json={"collapsed": True}).json()
    assert cv["columns"][0]["panels"][0]["collapsed"] is True and _events(client, w, "worklet.moved") == []


@needs_tmux
def test_detach_leaves_the_canvas_keeps_the_column_and_says_where(client):
    w = _work(client)
    client.patch(f"/api/works/{w['id']}/columns/c1", json={"alias": "调研"})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    client.delete(f"/api/works/{w['id']}/worklets/{s['id']}")
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert cv["columns"] == [{"id": "c1", "alias": "调研", "panels": [], "collapsed": False}]
    [e] = _events(client, w, "worklet.detached")
    assert e["data"]["column"] == {"id": "c1", "alias": "调研"} and e["data"]["uri"] == "bash://"


@needs_tmux
def test_worklet_ids_are_never_reused(client):
    w = _work(client)
    s1 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    client.delete(f"/api/works/{w['id']}/worklets/{s1['id']}")
    s2 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    assert s1["id"].endswith("-w1") and s2["id"].endswith("-w2")
