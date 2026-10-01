"""works/trace -- a work's history as OTel spans + points in worktrace.db, served as OTLP/JSON. See README.md."""
import hashlib
import threading

from memorytalk.backend.models.work import WorkletMove, WorkUpdate
from memorytalk.backend.services.work import WorkConflict
from tests._util import trace
from tests.conftest import needs_tmux

WEB = "https://example.com/x"          # http server 不起 tmux,开得快、永远活着


def _sha(text: str, n: int) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def _work(client, **kw):
    return client.post("/api/works", json={"goal": "x", **kw}).json()


def _spans(client, w, name, **kw):
    return [s for s in trace(client, w["id"], **kw)[0] if s["name"] == name]


def test_events_endpoint_is_gone(client):
    w = _work(client)
    assert client.get(f"/api/works/{w['id']}/events").status_code == 404


def test_create_opens_a_work_span(client, H):
    w = client.post("/api/works", json={"goal": "做 v5"}, headers=H("alice")).json()
    [s] = _spans(client, w, "work")
    assert s["end"] is None and s["memorytalk.open"] is True and s["status"] == 0 and s["parentSpanId"] is None
    assert (s["user.id"], s["memorytalk.work.id"], s["memorytalk.work.goal"]) == ("alice", w["id"], "做 v5")


def test_ids_are_derived_from_identity(client):
    root = _work(client)
    child = _work(client, parent=root["id"])
    m = client.post(f"/api/works/{child['id']}/worklets", json={"uri": WEB}).json()
    [rs] = _spans(client, root, "work")
    [cs] = _spans(client, child, "work")
    [ms] = _spans(client, child, "worklet")
    tid = _sha("memorytalk/trace/" + root["id"], 32)
    assert rs["traceId"] == cs["traceId"] == ms["traceId"] == tid                  # 一棵树一条 trace
    assert rs["spanId"] == _sha(f"memorytalk/span/work/{root['id']}/0", 16)
    assert cs["spanId"] == _sha(f"memorytalk/span/work/{child['id']}/0", 16) and cs["parentSpanId"] == rs["spanId"]
    assert ms["spanId"] == _sha(f"memorytalk/span/worklet/{m['id']}/0", 16) and ms["parentSpanId"] == cs["spanId"]


def test_response_is_otlp_json(client):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "右"})
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB}).json()
    client.post(f"/api/works/{w['id']}/worklets/{m['id']}/move", json={"column": "c2"})
    body = client.get(f"/api/works/{w['id']}/trace").json()
    [rs] = body["traces"]["resourceSpans"]
    assert {"key": "service.name", "value": {"stringValue": "memory.talk"}} in rs["resource"]["attributes"]
    [ss] = rs["scopeSpans"]
    assert ss["scope"] == {"name": "memorytalk.work", "version": "5"}
    work, worklet = ss["spans"]                                                      # 按开始时间排
    assert work["name"] == "work" and worklet["name"] == "worklet"
    assert work["kind"] == 1 and work["startTimeUnixNano"].isdigit() and "endTimeUnixNano" not in work
    assert {"key": "memorytalk.open", "value": {"boolValue": True}} in work["attributes"]
    assert len(work["traceId"]) == 32 and len(work["spanId"]) == 16 and work["status"] == {"code": 0}
    [rl] = body["logs"]["resourceLogs"]
    [sl] = rl["scopeLogs"]
    added, moved = sl["logRecords"]                                                  # 按先后排
    assert (added["eventName"], moved["eventName"]) == ("column.added", "worklet.moved")
    assert moved["timeUnixNano"] == moved["observedTimeUnixNano"] and moved["timeUnixNano"].isdigit()
    assert moved["traceId"] == work["traceId"] and moved["spanId"] == worklet["spanId"] and added["spanId"] == work["spanId"]
    assert {"key": "memorytalk.index", "value": {"intValue": "0"}} in moved["attributes"]


def test_archive_ends_the_work_span_and_open_worklet_spans(client, H):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB})
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"}, headers=H("bob"))
    spans, _ = trace(client, w["id"])
    assert all(s["end"] is not None and s["status"] == 1 and "memorytalk.open" not in s for s in spans)
    assert [(s["name"], s["memorytalk.end.reason"], s["memorytalk.end.user.id"]) for s in spans] == \
        [("work", "archived", "bob"), ("worklet", "archived", "bob")]
    assert spans[1]["memorytalk.end.column.id"] == "c1"
    assert spans[0]["user.id"] == "admin"                                            # 开它的人还在 user.id 上


def test_reopen_starts_a_new_segment_linked_to_the_previous(client):
    w = _work(client)
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    client.patch(f"/api/works/{w['id']}", json={"status": "running"})
    first, second = _spans(client, w, "work")
    assert first["end"] is not None and second["end"] is None
    assert second["spanId"] == _sha(f"memorytalk/span/work/{w['id']}/1", 16) and second["links"] == [first["spanId"]]
    assert second["memorytalk.work.reopened"] is True and second["traceId"] == first["traceId"]


def _in_another_thread(fn, *args):
    """另一个人的请求(FastAPI 的线程池里同时跑);等 0.3 秒,交回线程和它这会儿是不是还在等。"""
    t = threading.Thread(target=fn, args=args)
    t.start()
    t.join(timeout=0.3)
    return t, t.is_alive()


def test_a_reopen_mid_archive_waits_until_the_archive_is_done(client, svc, monkeypatch):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB}).json()
    real, reopen = svc.work_servers.destroy, []

    def destroy(server, worklet_id):                                   # 归档正在销毁现场,另一个人把它重新打开
        reopen.append(_in_another_thread(svc.works.update, w["id"], WorkUpdate(status="running"), "bob"))
        real(server, worklet_id)
    monkeypatch.setattr(svc.work_servers, "destroy", destroy)
    svc.works.update(w["id"], WorkUpdate(status="archived"), "alice")
    [(t, waiting)] = reopen
    t.join()
    assert waiting                                                     # 归档没做完,重新打开只能等着
    assert client.get(f"/api/works/{w['id']}").json()["status"] == "running"
    first, second = _spans(client, w, "work")
    assert (first["memorytalk.end.reason"], first["memorytalk.end.user.id"]) == ("archived", "alice")      # 归档结束的是它自己那段
    assert second["end"] is None and second["links"] == [first["spanId"]] and second["user.id"] == "bob"
    m0, m1 = _spans(client, w, "worklet")
    assert (m0["memorytalk.end.reason"], m0["memorytalk.end.user.id"]) == ("archived", "alice")
    assert m1["end"] is None and m1["parentSpanId"] == second["spanId"] and m1["memorytalk.worklet.id"] == m["id"]


def test_an_archive_mid_attach_waits_until_the_worklet_span_is_open(client, svc, monkeypatch):
    w = _work(client)
    real, archive = svc.works.trace.worklet_started, []

    def started(*a, **kw):                                             # 登记写进去了、段还没开,另一个人把 work 归档了
        archive.append(_in_another_thread(svc.works.update, w["id"], WorkUpdate(status="archived"), "bob"))
        real(*a, **kw)
    monkeypatch.setattr(svc.works.trace, "worklet_started", started)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB}).json()
    [(t, waiting)] = archive
    t.join()
    assert waiting and client.get(f"/api/works/{w['id']}").json()["status"] == "archived"
    spans, _ = trace(client, w["id"])
    assert [(s["name"], s.get("memorytalk.worklet.id"), s["memorytalk.end.reason"], s["memorytalk.end.user.id"]) for s in spans] == \
        [("work", None, "archived", "bob"), ("worklet", m["id"], "archived", "bob")]                   # 段开好了才归档,一起结束


def test_a_reattach_mid_archive_waits_and_is_refused(client, svc, monkeypatch):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB}).json()
    real, reattach, refused = svc.work_servers.destroy, [], []

    def reconnect():
        try:
            svc.works.reattach(w["id"], m["id"], "carol")
        except WorkConflict as e:
            refused.append(e)

    def destroy(server, worklet_id):                                   # 归档正在销毁现场,另一个人点了重连
        reattach.append(_in_another_thread(reconnect))
        real(server, worklet_id)
    monkeypatch.setattr(svc.work_servers, "destroy", destroy)
    svc.works.update(w["id"], WorkUpdate(status="archived"), "alice")
    [(t, waiting)] = reattach
    t.join()
    assert waiting and len(refused) == 1                               # 等归档做完,醒来看到已归档:409
    [s] = _spans(client, w, "worklet")                                 # 结束了的 work 段下面没再开出一段
    assert (s["memorytalk.end.reason"], s["memorytalk.end.user.id"]) == ("archived", "alice")


def test_no_reattach_in_an_archived_work(client, H):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"}, headers=H("bob"))
    r = client.post(f"/api/works/{w['id']}/worklets/{m['id']}/attach", headers=H("carol"))
    assert r.status_code == 409 and r.json()["error"] == "conflict"
    [s] = _spans(client, w, "worklet")
    assert s["memorytalk.end.reason"] == "archived"
    client.patch(f"/api/works/{w['id']}", json={"status": "running"}, headers=H("alice"))    # 重新打开之后又能重入了
    assert client.post(f"/api/works/{w['id']}/worklets/{m['id']}/attach", headers=H("carol")).status_code == 200
    first, second = _spans(client, w, "worklet")                       # 归档结束的一段 + 重新打开接着开的一段,中间没有长度为 0 的
    assert first["memorytalk.end.reason"] == "archived" and second["end"] is None and second["user.id"] == "alice"


def test_archive_reads_where_a_worklet_sits_in_one_go(client, svc, monkeypatch):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/columns", json={"alias": "右"})
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB, "column": "c2"}).json()
    real, fired, other = svc.works.repo.get_worklet, threading.Event(), []

    def move_back_and_drop_c2():
        svc.works.move_worklet(w["id"], m["id"], WorkletMove(column="c1"), "bob")
        svc.works.remove_column(w["id"], "c2", "bob")

    def get_worklet(*a):                                               # 归档读到它在 c2,还没读 c2 那一行,另一个人挪走它、删了 c2
        row = real(*a)
        if not fired.is_set():
            fired.set()
            other.append(_in_another_thread(move_back_and_drop_c2))
        return row
    monkeypatch.setattr(svc.works.repo, "get_worklet", get_worklet)
    svc.works.update(w["id"], WorkUpdate(status="archived"), "alice")   # 不报错
    [(t, waiting)] = other
    t.join()
    assert waiting                                                     # 两次读在一个事务里,挪 / 删得等它读完
    spans, _ = trace(client, w["id"])
    assert [(s["name"], s["memorytalk.end.reason"]) for s in spans] == [("work", "archived"), ("worklet", "archived")]
    assert spans[1]["memorytalk.end.column.id"] == "c2"                # 归档那一刻它在 c2
    assert [c["id"] for c in client.get(f"/api/works/{w['id']}/canvas").json()["columns"]] == ["c1"]


def test_reopen_ends_what_a_failed_archive_trace_left_open(client, svc, monkeypatch, H):
    w = _work(client)
    client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB})

    def boom(*a, **kw):
        raise RuntimeError("worktrace.db 坏了")
    with monkeypatch.context() as mp:
        mp.setattr(svc.works.trace, "work_archived", boom)
        client.patch(f"/api/works/{w['id']}", json={"status": "archived"}, headers=H("bob"))     # 归档照样成,段没结束上
    assert all(s["end"] is None for s in trace(client, w["id"])[0])
    client.patch(f"/api/works/{w['id']}", json={"status": "running"}, headers=H("carol"))
    first, second = _spans(client, w, "work")
    assert first["memorytalk.end.reason"] == "archived" and "memorytalk.end.user.id" not in first   # 先按归档补上终点,不知道是谁
    assert first["start"] <= first["end"] <= second["start"] and second["end"] is None and second["links"] == [first["spanId"]]
    m0, m1 = _spans(client, w, "worklet")
    assert m0["memorytalk.end.reason"] == "archived" and m0["end"] <= second["start"]
    assert m1["end"] is None and m1["parentSpanId"] == second["spanId"]
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"}, headers=H("alice"))
    assert [(s["end"] is not None, s.get("memorytalk.end.user.id")) for s in _spans(client, w, "work")] == \
        [(True, None), (True, "alice")]                                                    # 下一次归档结束的是新的一段


def test_archive_ends_every_open_work_span_not_just_the_latest(client, svc):
    w = _work(client)
    svc.works.trace.start(w["id"], "work", "f" * 16, None, {"memorytalk.work.id": w["id"]})     # 万一多出一段开着的
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    spans = _spans(client, w, "work")
    assert len(spans) == 2 and all(s["end"] is not None and s["memorytalk.end.reason"] == "archived" for s in spans)


def test_goal_change_is_a_work_renamed_point(client, H):
    w = client.post("/api/works", json={"goal": "旧"}, headers=H("alice")).json()
    client.patch(f"/api/works/{w['id']}", json={"goal": "新"}, headers=H("admin"))
    client.patch(f"/api/works/{w['id']}", json={"goal": "新"})                       # 没变不打点
    [s], [p] = _spans(client, w, "work"), trace(client, w["id"])[1]
    assert (p["event"], p["spanId"], p["user.id"], p["memorytalk.work.goal"], p["memorytalk.from"]) == \
        ("work.renamed", s["spanId"], "admin", "新", "旧")
    assert s["user.id"] == "alice"


def test_subtree_brings_in_the_descendants(client):
    root = _work(client)
    child = _work(client, parent=root["id"])
    grand = _work(client, parent=child["id"])
    assert [s["memorytalk.work.id"] for s in trace(client, root["id"])[0]] == [root["id"]]
    assert {s["memorytalk.work.id"] for s in trace(client, root["id"], subtree=True)[0]} == {root["id"], child["id"], grand["id"]}
    assert client.get("/api/works/work_nope/trace").status_code == 404


def test_detach_ends_the_worklet_span_with_who_closed_it(client, H):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB}, headers=H("alice")).json()
    client.delete(f"/api/works/{w['id']}/worklets/{m['id']}", headers=H("bob"))
    [s] = _spans(client, w, "worklet")
    assert (s["user.id"], s["memorytalk.end.user.id"], s["memorytalk.end.reason"], s["status"]) == ("alice", "bob", "detached", 1)
    assert (s["memorytalk.worklet.uri"], s["memorytalk.worklet.scheme"], s["memorytalk.worklet.server"]) == (WEB, "https", "http")


def test_a_failing_trace_does_not_fail_the_action(client, svc, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("worktrace.db 坏了")
    with monkeypatch.context() as mp:
        mp.setattr(svc.works.trace_repo, "insert_span", boom)
        mp.setattr(svc.works.trace_repo, "insert_point", boom)
        w = _work(client)
        assert w["status"] == "running"
        r = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB})
        assert r.status_code == 201
        assert client.post(f"/api/works/{w['id']}/columns", json={}).status_code == 201
    cv = client.get(f"/api/works/{w['id']}/canvas").json()
    assert [p["worklet"] for p in cv["columns"][0]["panels"]] == [r.json()["id"]]       # work 照常,只是轨迹少了
    assert trace(client, w["id"]) == ([], [])


@needs_tmux
def test_a_vanished_site_ends_its_span_as_gone_and_reattach_opens_a_new_one(client, svc, home):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    svc.work_servers.destroy("bash", m["id"])                                           # 现场自己没了
    assert client.get(f"/api/works/{w['id']}/worklets").json()[0]["alive"] is False
    [s] = _spans(client, w, "worklet")
    assert s["end"] is not None and s["status"] == 0 and s["memorytalk.end.reason"] == "gone" and "memorytalk.end.user.id" not in s
    client.post(f"/api/works/{w['id']}/worklets/{m['id']}/attach")
    client.post(f"/api/works/{w['id']}/worklets/{m['id']}/attach")                    # 已经开着就不再开
    first, second = _spans(client, w, "worklet")
    assert second["end"] is None and second["spanId"] == _sha(f"memorytalk/span/worklet/{m['id']}/1", 16)


def test_reopen_resumes_live_worklets_so_closing_them_is_recorded(client, H):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": WEB}, headers=H("alice")).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"}, headers=H("bob"))
    client.patch(f"/api/works/{w['id']}", json={"status": "running"}, headers=H("bob"))     # 网页的现场一直活着,没人会去重连
    _, work2 = _spans(client, w, "work")
    first, second = _spans(client, w, "worklet")
    assert first["memorytalk.end.reason"] == "archived" and second["end"] is None
    assert second["spanId"] == _sha(f"memorytalk/span/worklet/{m['id']}/1", 16) and second["parentSpanId"] == work2["spanId"]
    assert (second["user.id"], second["memorytalk.column.id"]) == ("bob", "c1")
    client.post(f"/api/works/{w['id']}/columns", json={})
    client.post(f"/api/works/{w['id']}/worklets/{m['id']}/move", json={"column": "c2"}, headers=H("carol"))
    client.delete(f"/api/works/{w['id']}/worklets/{m['id']}", headers=H("carol"))
    _, second = _spans(client, w, "worklet")
    assert (second["memorytalk.end.reason"], second["memorytalk.end.user.id"], second["memorytalk.end.column.id"]) == ("detached", "carol", "c2")
    [moved] = [p for p in trace(client, w["id"])[1] if p["event"] == "worklet.moved"]
    assert moved["spanId"] == second["spanId"]                                           # 挪动挂在开着的那一段上


@needs_tmux
def test_closing_a_worklet_without_an_open_span_is_a_point(client, home, H):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}, headers=H("alice")).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"}, headers=H("bob"))     # 现场销毁了,段 archived
    client.patch(f"/api/works/{w['id']}", json={"status": "running"}, headers=H("bob"))      # 不重连,直接关掉
    assert client.delete(f"/api/works/{w['id']}/worklets/{m['id']}", headers=H("carol")).status_code == 200
    [s] = _spans(client, w, "worklet")
    assert s["memorytalk.end.reason"] == "archived" and s["memorytalk.end.user.id"] == "bob"   # 结束了的段不再动
    [p] = [p for p in trace(client, w["id"])[1] if p["event"] == "worklet.closed"]
    assert (p["spanId"], p["user.id"], p["memorytalk.worklet.id"], p["memorytalk.column.id"], p["memorytalk.column.alias"]) == \
        (s["spanId"], "carol", m["id"], "c1", "")
    assert client.get("/api/users/carol").json()["works_touched_ids"] == [w["id"]]       # 关掉也算动过


@needs_tmux
def test_closing_a_gone_worklet_is_a_point(client, svc, home, H):
    w = _work(client)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    svc.work_servers.destroy("bash", m["id"])
    client.get(f"/api/works/{w['id']}/worklets")                                         # 段结束成 gone
    client.delete(f"/api/works/{w['id']}/worklets/{m['id']}", headers=H("bob"))
    [s] = _spans(client, w, "worklet")
    [p] = trace(client, w["id"])[1]
    assert s["memorytalk.end.reason"] == "gone" and (p["event"], p["spanId"], p["user.id"]) == ("worklet.closed", s["spanId"], "bob")
