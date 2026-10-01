"""works/canvas -- columns (fixed number + alias) of worklets, one request per action. See README.md."""
from tests._util import trace
from tests.conftest import needs_tmux


def _work(client):
    return client.post("/api/works", json={"goal": "x"}).json()


def _points(client, w, prefix=""):
    return [p for p in trace(client, w["id"])[1] if p["event"].startswith(prefix)]


def _span(client, w, name, **attrs):
    [s] = [s for s in trace(client, w["id"])[0] if s["name"] == name and all(s.get(k) == v for k, v in attrs.items())]
    return s


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


def test_rename_only_changes_the_alias_and_is_a_point(client, H):
    w = _work(client)
    cv = client.patch(f"/api/works/{w['id']}/columns/c1", json={"alias": " 测试 "}, headers=H("alice")).json()
    assert cv["columns"][0] == {"id": "c1", "alias": "测试", "panels": [], "collapsed": False}
    [p] = _points(client, w, "column.")
    assert p["event"] == "column.renamed" and p["spanId"] == _span(client, w, "work")["spanId"]
    assert {k: p[k] for k in ("user.id", "memorytalk.column.id", "memorytalk.column.alias", "memorytalk.from")} == \
        {"user.id": "alice", "memorytalk.column.id": "c1", "memorytalk.column.alias": "测试", "memorytalk.from": ""}


def test_collapse_column_is_not_a_point(client):
    w = _work(client)
    assert client.patch(f"/api/works/{w['id']}/columns/c1", json={"collapsed": True}).json()["columns"][0]["collapsed"] is True
    assert _points(client, w, "column.") == []


def test_add_and_remove_column_are_points(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "右"})
    client.delete(f"/api/works/{w['id']}/columns/c2")
    assert [(p["event"], p["memorytalk.column.id"], p["memorytalk.column.alias"]) for p in _points(client, w, "column.")] == \
        [("column.added", "c2", "右"), ("column.removed", "c2", "右")]


def test_last_column_cannot_be_removed(client):
    w = _work(client)
    assert client.delete(f"/api/works/{w['id']}/columns/c1").status_code == 409


def test_column_ids_must_be_c_number(client):
    w = _work(client)
    for bad in ("1", "left", "c1x", "C1", "c01"):
        assert client.patch(f"/api/works/{w['id']}/columns/{bad}", json={"alias": "x"}).status_code == 404


def test_unknown_column_is_404(client):
    w = _work(client)
    assert client.patch(f"/api/works/{w['id']}/columns/c9", json={"alias": "x"}).status_code == 404
    assert client.post(f"/api/works/{w['id']}/columns", json={"beside": "c9"}).status_code == 404
    assert client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c9"}).status_code == 404


def test_column_numbers_too_big_to_exist_are_404(client):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "https://example.com/x"}).json()   # 网页的不起 tmux
    for bad in ("c9223372036854775807", "c9223372036854775808", "c" + "9" * 5000):            # sqlite 整数的上限、再大一个、int() 都解不了的位数
        assert client.patch(f"/api/works/{w['id']}/columns/{bad}", json={"alias": "x"}).status_code == 404
        assert client.delete(f"/api/works/{w['id']}/columns/{bad}").status_code == 404
        assert client.post(f"/api/works/{w['id']}/columns", json={"beside": bad}).status_code == 404
        assert client.post(f"/api/works/{w['id']}/worklets/{m['id']}/move", json={"column": bad}).status_code == 404
        assert client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": bad}).status_code == 404
    assert client.get(f"/api/works/{w['id']}/canvas").json()["version"] == 1                 # 只有打开那一次


def test_put_canvas_is_gone(client):
    w = _work(client)
    assert client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "columns": []}).status_code == 405


@needs_tmux
def test_attach_lands_in_the_given_column_and_the_span_says_so(client, H):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "测试"})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c2"}, headers=H("alice")).json()
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert [[p["worklet"] for p in c["panels"]] for c in cv["columns"]] == [[], [s["id"]]]
    assert cv["version"] == 2                                       # 加列一次、打开(摆上)一次
    span = _span(client, w, "worklet")
    assert span["end"] is None and span["parentSpanId"] == _span(client, w, "work")["spanId"]
    assert (span["user.id"], span["memorytalk.worklet.id"], span["memorytalk.column.id"], span["memorytalk.column.alias"]) == \
        ("alice", s["id"], "c2", "测试")


@needs_tmux
def test_a_column_with_worklets_cannot_be_removed(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={})
    client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c2"})
    assert client.delete(f"/api/works/{w['id']}/columns/c2").status_code == 409
    assert [c["id"] for c in client.get(f"/api/works/{w['id']}/canvas").json()["columns"]] == ["c1", "c2"]


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
    first = _points(client, w, "worklet.moved")[0]
    assert first["spanId"] == _span(client, w, "worklet", **{"memorytalk.worklet.id": s1["id"]})["spanId"]
    assert {k: v for k, v in first.items() if k.startswith(("user.", "memorytalk."))} == {
        "user.id": "bob", "memorytalk.worklet.id": s1["id"],
        "memorytalk.from.column.id": "c1", "memorytalk.from.column.alias": "", "memorytalk.from.index": 0,
        "memorytalk.column.id": "c2", "memorytalk.column.alias": "右", "memorytalk.index": 0}


@needs_tmux
def test_move_keeps_positions_contiguous_and_clamps_the_index(client):
    w = _work(client)
    a, b, c = (client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()["id"] for _ in range(3))
    col = lambda cv: [p["worklet"] for p in cv["columns"][0]["panels"]]
    assert col(client.post(f"/api/works/{w['id']}/worklets/{a}/move", json={"column": "c1", "index": 9}).json()) == [b, c, a]
    assert col(client.post(f"/api/works/{w['id']}/worklets/{a}/move", json={"column": "c1", "index": 1}).json()) == [b, a, c]
    cv = client.post(f"/api/works/{w['id']}/worklets/{a}/move", json={"column": "c1", "index": 1}).json()     # 原地不动
    assert col(cv) == [b, a, c] and [p["event"] for p in _points(client, w, "worklet.moved")] == ["worklet.moved"] * 2
    client.delete(f"/api/works/{w['id']}/worklets/{b}")
    cv = client.post(f"/api/works/{w['id']}/worklets/{c}/move", json={"column": "c1", "index": 0}).json()
    assert col(cv) == [c, a]


@needs_tmux
def test_collapse_worklet_is_not_a_point(client):
    w = _work(client)
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    cv = client.patch(f"/api/works/{w['id']}/worklets/{s['id']}", json={"collapsed": True}).json()
    assert cv["columns"][0]["panels"][0]["collapsed"] is True and _points(client, w) == []


@needs_tmux
def test_detach_leaves_the_canvas_keeps_the_column_and_says_where(client):
    w = _work(client)
    client.patch(f"/api/works/{w['id']}/columns/c1", json={"alias": "调研"})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    client.delete(f"/api/works/{w['id']}/worklets/{s['id']}")
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert cv["columns"] == [{"id": "c1", "alias": "调研", "panels": [], "collapsed": False}]
    span = _span(client, w, "worklet")
    assert span["end"] is not None and span["status"] == 1 and span["memorytalk.end.reason"] == "detached"
    assert (span["memorytalk.end.column.id"], span["memorytalk.end.column.alias"], span["memorytalk.worklet.uri"]) == ("c1", "调研", "bash://")


@needs_tmux
def test_worklet_ids_are_never_reused(client):
    w = _work(client)
    s1 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    client.delete(f"/api/works/{w['id']}/worklets/{s1['id']}")
    s2 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    assert s1["id"].endswith("-w1") and s2["id"].endswith("-w2")
