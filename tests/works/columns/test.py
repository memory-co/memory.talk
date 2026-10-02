"""works/columns -- columns (fixed number + alias) and where each worklet sits, one request per action. See README.md."""
from tests._util import trace
from tests.conftest import needs_tmux


def _work(client):
    return client.post("/api/works", json={"goal": "x"}).json()


def _points(client, w, prefix=""):
    return [p for p in trace(client, w["id"])[1] if p["event"].startswith(prefix)]


def _span(client, w, name, **attrs):
    [s] = [s for s in trace(client, w["id"])[0] if s["name"] == name and all(s.get(k) == v for k, v in attrs.items())]
    return s


def _columns(client, w):
    return client.get(f"/api/works/{w['id']}/columns").json()


def _worklets(client, w):
    return client.get(f"/api/works/{w['id']}/worklets").json()


def _where(worklets):
    """[(工作单元, 列, 列里第几个)],按开的先后。"""
    return [(m["id"], m["column"], m["position"]) for m in worklets]


def _in(worklets, column):
    """某一列里从上到下是哪几个。"""
    return [m["id"] for m in sorted((m for m in worklets if m["column"] == column), key=lambda m: m["position"])]


def test_fresh_work_has_one_column_c1(client):
    w = _work(client)
    assert _columns(client, w) == [{"id": "c1", "alias": "", "collapsed": False, "position": 0}]


def test_canvas_is_gone(client):
    w = _work(client)
    assert client.get(f"/api/works/{w['id']}/canvas").status_code == 404
    assert client.put(f"/api/works/{w['id']}/canvas", json={"columns": []}).status_code == 404


def test_add_column_numbers_are_monotonic_and_never_reused(client):
    w = _work(client)
    base = f"/api/works/{w['id']}/columns"
    r = client.post(base, json={})
    assert r.status_code == 201 and [c["id"] for c in r.json()] == ["c1", "c2"]
    client.delete(f"{base}/c2")
    cols = client.post(base, json={"alias": "调研", "beside": "c1", "side": "left"}).json()
    assert [(c["id"], c["alias"], c["position"]) for c in cols] == [("c3", "调研", 0), ("c1", "", 1)]      # c2 删了也不再发
    assert _columns(client, w) == cols


def test_add_column_left_or_right_of_beside(client):
    w = _work(client)
    base = f"/api/works/{w['id']}/columns"
    client.post(base, json={})                                                         # c1 c2
    assert [c["id"] for c in client.post(base, json={"beside": "c1", "side": "right"}).json()] == ["c1", "c3", "c2"]
    assert [c["id"] for c in client.post(base, json={"beside": "c2", "side": "left"}).json()] == ["c1", "c3", "c4", "c2"]
    assert [c["position"] for c in _columns(client, w)] == [0, 1, 2, 3]


def test_column_ops_return_the_column_list(client):
    w = _work(client)
    base = f"/api/works/{w['id']}/columns"
    added = client.post(base, json={"alias": "右"}).json()
    renamed = client.patch(f"{base}/c2", json={"alias": "右边"}).json()
    removed = client.delete(f"{base}/c2").json()
    assert [c["id"] for c in added] == ["c1", "c2"] and renamed[1]["alias"] == "右边"
    assert removed == [{"id": "c1", "alias": "", "collapsed": False, "position": 0}] == _columns(client, w)


def test_rename_only_changes_the_alias_and_is_a_point(client, H):
    w = _work(client)
    cols = client.patch(f"/api/works/{w['id']}/columns/c1", json={"alias": " 测试 "}, headers=H("alice")).json()
    assert cols == [{"id": "c1", "alias": "测试", "collapsed": False, "position": 0}]
    [p] = _points(client, w, "column.")
    assert p["event"] == "column.renamed" and p["spanId"] == _span(client, w, "work")["spanId"]
    assert {k: p[k] for k in ("user.id", "memorytalk.column.id", "memorytalk.column.alias", "memorytalk.from")} == \
        {"user.id": "alice", "memorytalk.column.id": "c1", "memorytalk.column.alias": "测试", "memorytalk.from": ""}


def test_collapse_column_is_not_a_point(client):
    w = _work(client)
    assert client.patch(f"/api/works/{w['id']}/columns/c1", json={"collapsed": True}).json()[0]["collapsed"] is True
    assert _columns(client, w)[0]["collapsed"] is True
    assert _points(client, w, "column.") == []


def test_add_and_remove_column_are_points(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "右"})
    client.delete(f"/api/works/{w['id']}/columns/c2")
    assert [(p["event"], p["memorytalk.column.id"], p["memorytalk.column.alias"]) for p in _points(client, w, "column.")] == \
        [("column.added", "c2", "右"), ("column.removed", "c2", "右")]


def test_removing_a_column_keeps_positions_contiguous(client):
    w = _work(client)
    base = f"/api/works/{w['id']}/columns"
    client.post(base, json={})
    client.post(base, json={})
    assert [(c["id"], c["position"]) for c in client.delete(f"{base}/c2").json()] == [("c1", 0), ("c3", 1)]


def test_last_column_cannot_be_removed(client):
    w = _work(client)
    assert client.delete(f"/api/works/{w['id']}/columns/c1").status_code == 409
    assert [c["id"] for c in _columns(client, w)] == ["c1"]


def test_column_ids_must_be_c_number(client):
    w = _work(client)
    for bad in ("1", "left", "c1x", "C1", "c01"):
        assert client.patch(f"/api/works/{w['id']}/columns/{bad}", json={"alias": "x"}).status_code == 404


def test_unknown_column_is_404(client):
    w = _work(client)
    assert client.patch(f"/api/works/{w['id']}/columns/c9", json={"alias": "x"}).status_code == 404
    assert client.post(f"/api/works/{w['id']}/columns", json={"beside": "c9"}).status_code == 404
    assert client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c9"}).status_code == 404


def test_columns_of_an_unknown_work_is_404(client):
    assert client.get("/api/works/work_nope/columns").status_code == 404


def test_column_numbers_too_big_to_exist_are_404(client):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "https://example.com/x"}).json()   # 网页的不起 tmux
    for bad in ("c9223372036854775807", "c9223372036854775808", "c" + "9" * 5000):            # sqlite 整数的上限、再大一个、int() 都解不了的位数
        assert client.patch(f"/api/works/{w['id']}/columns/{bad}", json={"alias": "x"}).status_code == 404
        assert client.delete(f"/api/works/{w['id']}/columns/{bad}").status_code == 404
        assert client.post(f"/api/works/{w['id']}/columns", json={"beside": bad}).status_code == 404
        assert client.post(f"/api/works/{w['id']}/worklets/{m['id']}/move", json={"column": bad}).status_code == 404
        assert client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": bad}).status_code == 404
    assert _columns(client, w) == [{"id": "c1", "alias": "", "collapsed": False, "position": 0}]   # 什么都没动
    assert _where(_worklets(client, w)) == [(m["id"], "c1", 0)]


def test_worklets_carry_column_position_and_collapsed(client):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "https://example.com/x"}).json()
    assert (m["column"], m["position"], m["collapsed"]) == ("c1", 0, False)
    [v] = _worklets(client, w)
    assert (v["id"], v["column"], v["position"], v["collapsed"]) == (m["id"], "c1", 0, False)


def test_move_and_collapse_return_the_worklet_list(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={})
    a, b = (client.post(f"/api/works/{w['id']}/worklets", json={"uri": "https://example.com/x"}).json()["id"] for _ in range(2))
    moved = client.post(f"/api/works/{w['id']}/worklets/{a}/move", json={"column": "c2"}).json()
    assert _where(moved) == [(a, "c2", 0), (b, "c1", 0)] == _where(_worklets(client, w))       # 按开的先后排,各自带在哪
    collapsed = client.patch(f"/api/works/{w['id']}/worklets/{b}", json={"collapsed": True}).json()
    assert [(m["id"], m["collapsed"]) for m in collapsed] == [(a, False), (b, True)]


def test_column_removed_while_the_site_opens_is_404_and_leaves_nothing(client, svc, monkeypatch):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={})
    real_open, real_destroy, destroyed = svc.work_servers.open, svc.work_servers.destroy, []

    def open_while_removing(*a, **kw):                                   # 先验过了列在,现场还在建,另一个人把列删了
        svc.works.remove_column(w["id"], "c2", "bob")
        return real_open(*a, **kw)

    def destroy(server, worklet_id):
        destroyed.append(worklet_id)
        real_destroy(server, worklet_id)
    monkeypatch.setattr(svc.work_servers, "open", open_while_removing)
    monkeypatch.setattr(svc.work_servers, "destroy", destroy)
    r = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "https://example.com/x", "column": "c2"})
    assert (r.status_code, r.json()["error"], r.json()["message"]) == (404, "not_found", "c2")    # 列没了是 404,不是 409
    assert destroyed == [f"{w['id']}-w1"]                                                   # 建起来的现场收掉了
    assert _worklets(client, w) == [] and [c["id"] for c in _columns(client, w)] == ["c1"]
    assert [s["name"] for s in trace(client, w["id"])[0]] == ["work"]                       # 不开 worklet 段


def test_move_or_collapse_an_unknown_worklet_is_404(client):
    w = _work(client)
    assert client.post(f"/api/works/{w['id']}/worklets/{w['id']}-w9/move", json={"column": "c1"}).status_code == 404
    assert client.patch(f"/api/works/{w['id']}/worklets/{w['id']}-w9", json={"collapsed": True}).status_code == 404


@needs_tmux
def test_attach_lands_in_the_given_column_and_the_span_says_so(client, H):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "测试"})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c2"}, headers=H("alice")).json()
    assert (s["column"], s["position"]) == ("c2", 0)
    assert _where(_worklets(client, w)) == [(s["id"], "c2", 0)]
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
    assert [c["id"] for c in _columns(client, w)] == ["c1", "c2"]


@needs_tmux
def test_attach_without_column_goes_to_the_leftmost(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"beside": "c1", "side": "left"})
    assert _columns(client, w)[0]["id"] == "c2"
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    assert (s["column"], s["position"]) == ("c2", 0) and _where(_worklets(client, w)) == [(s["id"], "c2", 0)]


@needs_tmux
def test_attach_appends_to_the_end_of_the_column(client):
    w = _work(client)
    a, b = (client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json() for _ in range(2))
    assert [(a["column"], a["position"]), (b["column"], b["position"])] == [("c1", 0), ("c1", 1)]


@needs_tmux
def test_move_between_and_within_columns(client, H):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "右"})
    s1 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    s2 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    ms = client.post(f"/api/works/{w['id']}/worklets/{s1['id']}/move", json={"column": "c2"}, headers=H("bob")).json()
    assert (_in(ms, "c1"), _in(ms, "c2")) == ([s2["id"]], [s1["id"]])
    ms = client.post(f"/api/works/{w['id']}/worklets/{s1['id']}/move", json={"column": "c1", "index": 0}).json()
    assert _in(ms, "c1") == [s1["id"], s2["id"]] and _where(ms) == [(s1["id"], "c1", 0), (s2["id"], "c1", 1)]
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
    move = lambda x, **kw: client.post(f"/api/works/{w['id']}/worklets/{x}/move", json={"column": "c1", **kw}).json()
    assert _in(move(a, index=9), "c1") == [b, c, a]
    assert _in(move(a, index=1), "c1") == [b, a, c]
    ms = move(a, index=1)                                                               # 原地不动
    assert _in(ms, "c1") == [b, a, c] and [p["event"] for p in _points(client, w, "worklet.moved")] == ["worklet.moved"] * 2
    assert sorted(m["position"] for m in ms) == [0, 1, 2]
    client.delete(f"/api/works/{w['id']}/worklets/{b}")
    assert _where(_worklets(client, w)) == [(a, "c1", 0), (c, "c1", 1)]                # 关掉的后面往上补
    ms = move(c, index=0)
    assert _in(ms, "c1") == [c, a] and sorted(m["position"] for m in ms) == [0, 1]
    assert _in(move(c), "c1") == [a, c]                                                # 不给 index = 末尾


@needs_tmux
def test_collapse_worklet_is_not_a_point(client):
    w = _work(client)
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    ms = client.patch(f"/api/works/{w['id']}/worklets/{s['id']}", json={"collapsed": True}).json()
    assert ms[0]["collapsed"] is True and _worklets(client, w)[0]["collapsed"] is True and _points(client, w) == []


@needs_tmux
def test_detach_keeps_the_column_and_says_where(client):
    w = _work(client)
    client.patch(f"/api/works/{w['id']}/columns/c1", json={"alias": "调研"})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    client.delete(f"/api/works/{w['id']}/worklets/{s['id']}")
    assert _columns(client, w) == [{"id": "c1", "alias": "调研", "collapsed": False, "position": 0}]
    assert _worklets(client, w) == []
    span = _span(client, w, "worklet")
    assert span["end"] is not None and span["status"] == 1 and span["memorytalk.end.reason"] == "detached"
    assert (span["memorytalk.end.column.id"], span["memorytalk.end.column.alias"], span["memorytalk.worklet.uri"]) == ("c1", "调研", "bash://")


@needs_tmux
def test_reattach_says_where_the_worklet_is(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={})
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://", "column": "c2"}).json()
    r = client.post(f"/api/works/{w['id']}/worklets/{s['id']}/attach").json()
    assert (r["id"], r["column"], r["position"], r["collapsed"]) == (s["id"], "c2", 0, False)


@needs_tmux
def test_worklet_ids_are_never_reused(client):
    w = _work(client)
    s1 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    client.delete(f"/api/works/{w['id']}/worklets/{s1['id']}")
    s2 = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).json()
    assert s1["id"].endswith("-w1") and s2["id"].endswith("-w2")
