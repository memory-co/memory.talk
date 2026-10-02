"""works/trace_push —— POST /works/{id}/trace(节点写)和 GET 的 worklet / agent / bodies / after / wait / fields。见 README.md。"""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from memorytalk.backend.gateway import NodeSocket
from memorytalk.node import otlp
from tests._util import trace
from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def node(client):
    """从中心给节点开的 unix socket 上来的请求:同一个 app,前面套一层 NodeSocket(和 serve.py 里一样)。"""
    return TestClient(NodeSocket(client.app))


@pytest.fixture
def site(client):
    w = client.post("/api/works", json={"goal": "推上来"}).json()
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash:///tmp"}).json()
    spans, _ = trace(client, w["id"])
    [seg] = [s for s in spans if s["name"] == "worklet"]
    return w["id"], m["id"], seg


def doc(spans=(), records=()):
    return otlp.document(list(spans), list(records))


def at(site, n):
    """worklet 段开始之后第 n 纳秒。"""
    return site[2]["start"] + n


def session(site, sid="s1", end=None, **attrs):
    work, m, seg = site
    return otlp.span(seg["traceId"], otlp.session_span_id(m, sid, f"{m}:u0"), seg["spanId"], "agent.session", at(site, 1),
                     {"memorytalk.worklet.id": m, "gen_ai.conversation.id": sid, **attrs},
                     end=None if end is None else at(site, end), status=1 if end else 0)


def message(site, uid, text, span_id, n=2):
    work, m, seg = site
    return otlp.record(seg["traceId"], span_id, "agent.message", at(site, n), f"{m}:{uid}",
                       {"memorytalk.worklet.id": m, "memorytalk.message.role": "user", "memorytalk.message.kind": "text"}, text)


def push(node, work, body, **kw):
    return node.post(f"/api/works/{work}/trace", json={**body, **kw})


def test_a_logged_in_user_can_read_but_not_write(client, site):
    work, _, _ = site
    r = client.post(f"/api/works/{work}/trace", json=doc())
    assert r.status_code == 403 and r.json()["error"] == "forbidden"


def test_the_node_can_only_reach_the_trace(node, site):
    assert node.get("/api/works").status_code == 403
    assert node.get(f"/api/works/{site[0]}/trace").status_code == 200


def test_pushed_spans_and_points_are_read_back_as_they_were(client, node, site):
    work, m, seg = site
    s = session(site)
    r = push(node, work, doc([s], [message(site, "u1", "你好", s["spanId"])]))
    assert r.json() == {"spans": {"inserted": 1, "ended": 0, "merged": 0, "ignored": 0}, "points": {"inserted": 1, "duplicate": 0}}
    spans, points = trace(client, work)
    [got] = [x for x in spans if x["name"] == "agent.session"]
    assert (got["spanId"], got["parentSpanId"], got["end"], got["memorytalk.open"]) == (s["spanId"], seg["spanId"], None, True)
    [p] = points
    assert (p["event"], p["spanId"], p["time"], p["body"], p["log.record.uid"]) == ("agent.message", s["spanId"], at(site, 2), "你好", f"{m}:u1")


def test_the_received_time_is_the_centers(client, node, site):
    work, _, _ = site
    s = session(site)
    push(node, work, doc([s], [message(site, "u1", "你好", s["spanId"])]))
    body = client.get(f"/api/works/{work}/trace", params={"agent": 1}).json()
    [r] = body["logs"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
    assert r["timeUnixNano"] == str(at(site, 2)) and int(r["observedTimeUnixNano"]) > time.time_ns() - 60 * 10**9


def test_by_default_agent_layers_and_bodies_stay_out(client, node, site):
    work, _, _ = site
    s = session(site)
    push(node, work, doc([s], [message(site, "u1", "你好", s["spanId"])]))
    spans, points = trace(client, work, agent=False)
    assert [x["name"] for x in spans] == ["work", "worklet"] and points == []
    body = client.get(f"/api/works/{work}/trace", params={"agent": 1}).json()
    assert "body" not in body["logs"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]


def test_worklet_narrows_to_one_worklet(client, node, site):
    work, m, _ = site
    other = client.post(f"/api/works/{work}/worklets", json={"uri": "bash:///tmp"}).json()
    s = session(site)
    push(node, work, doc([s], [message(site, "u1", "你好", s["spanId"])]))
    spans, points = trace(client, work, worklet=other["id"])
    assert [x["name"] for x in spans] == ["worklet"] and points == []
    spans, points = trace(client, work, worklet=m)
    assert [x["name"] for x in spans] == ["worklet", "agent.session"] and len(points) == 1


def test_pushing_the_same_batch_twice_changes_nothing(client, node, site):
    work, _, _ = site
    s = session(site)
    body = doc([s], [message(site, "u1", "你好", s["spanId"])])
    push(node, work, body)
    before = client.get(f"/api/works/{work}/trace", params={"agent": 1}).json()["seq"]
    assert push(node, work, body).json() == {"spans": {"inserted": 0, "ended": 0, "merged": 0, "ignored": 1},
                                             "points": {"inserted": 0, "duplicate": 1}}
    assert client.get(f"/api/works/{work}/trace", params={"agent": 1}).json()["seq"] == before


def test_an_open_span_merges_attributes_until_it_ends_and_then_it_is_final(client, node, site):
    work, _, _ = site
    push(node, work, doc([session(site, **{"memorytalk.unrecognized": 0})]))
    assert push(node, work, doc([session(site, **{"memorytalk.unrecognized": 2})])).json()["spans"]["merged"] == 1
    assert push(node, work, doc([session(site, end=5, **{"memorytalk.end.reason": "replaced"})])).json()["spans"]["ended"] == 1
    assert push(node, work, doc([session(site, **{"memorytalk.unrecognized": 9})])).json()["spans"]["ignored"] == 1
    [s] = [x for x in trace(client, work)[0] if x["name"] == "agent.session"]
    assert (s["memorytalk.unrecognized"], s["end"], s["status"], s["memorytalk.end.reason"]) == (2, at(site, 5), 1, "replaced")


def test_a_point_without_uid_rejects_the_whole_batch(client, node, site):
    work, m, seg = site
    s = session(site)
    bad = otlp.record(seg["traceId"], s["spanId"], "agent.message", 1, "x", {"memorytalk.worklet.id": m}, "hi")
    bad["attributes"] = [kv for kv in bad["attributes"] if kv["key"] != "log.record.uid"]
    r = push(node, work, doc([s], [bad]))
    assert r.status_code == 422 and r.json()["error"] == "invalid"
    assert [x["name"] for x in trace(client, work)[0]] == ["work", "worklet"]            # 一个事务:段也没写


def test_the_node_cannot_write_what_the_center_writes(node, site):
    work, m, seg = site
    work_span = otlp.span(seg["traceId"], "ab" * 8, None, "work", 1, {})
    assert push(node, work, doc([work_span])).status_code == 403
    reopen = otlp.span(seg["traceId"], seg["spanId"], None, "worklet", 1, {"memorytalk.end.reason": "detached"}, end=2)
    assert push(node, work, doc([reopen])).status_code == 403                             # worklet 段只能补 gone
    act = otlp.record(seg["traceId"], None, "worklet.moved", 1, f"{m}:x", {"memorytalk.worklet.id": m})
    assert push(node, work, doc([], [act])).status_code == 403


def test_a_record_of_another_works_worklet_is_rejected(client, node, site):
    work, _, _ = site
    other = client.post("/api/works", json={"goal": "别的"}).json()
    r = push(node, other["id"], doc([session(site)]))
    assert r.status_code == 422


def test_the_node_reports_gone_and_the_open_agent_spans_follow(client, node, site, svc):
    work, m, seg = site
    s = session(site)
    push(node, work, doc([s]))
    gone = otlp.span(seg["traceId"], seg["spanId"], None, "worklet", 1, {"memorytalk.end.reason": "gone"}, end=at(site, 9))
    assert push(node, work, doc([gone])).json()["spans"]["ignored"] == 1                 # 现场还活着:不收
    svc.work_servers.destroy("bash", m)
    assert push(node, work, doc([gone])).json()["spans"]["ended"] == 1
    spans, _ = trace(client, work)
    [w] = [x for x in spans if x["name"] == "worklet"]
    [a] = [x for x in spans if x["name"] == "agent.session"]
    assert (w["memorytalk.end.reason"], w["status"], w["memorytalk.end.column.id"]) == ("gone", 0, "c1")
    assert (a["memorytalk.end.reason"], a["status"]) == ("gone", 0)


def test_cursors_are_stored_with_the_batch_and_read_back(client, node, site):
    work, m, _ = site
    push(node, work, doc([session(site)]), cursors=[{"worklet_id": m, "source": "hooks", "position": "120"}])
    push(node, work, doc(), cursors=[{"worklet_id": m, "source": "hooks", "position": "300"}])
    got = node.get(f"/api/works/{work}/trace", params={"worklet": m, "fields": "cursors"}).json()
    assert [(c["source"], c["position"]) for c in got["cursors"]] == [("hooks", "300")] and "traces" not in got
    assert node.get(f"/api/works/{work}/trace", params={"fields": "cursors"}).status_code == 422


def test_after_gives_only_what_changed(client, node, site):
    work, _, _ = site
    s = session(site)
    push(node, work, doc([s]))
    seq = client.get(f"/api/works/{work}/trace", params={"agent": 1}).json()["seq"]
    push(node, work, doc([], [message(site, "u1", "新的一条", s["spanId"])]))
    body = client.get(f"/api/works/{work}/trace", params={"agent": 1, "bodies": 1, "after": seq}).json()
    assert body["traces"]["resourceSpans"][0]["scopeSpans"][0]["spans"] == []
    assert [r["body"]["stringValue"] for r in body["logs"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]] == ["新的一条"]
    assert int(body["seq"]) > int(seq)


def test_an_ended_span_shows_up_after_its_seq(client, node, site):
    work, _, _ = site
    push(node, work, doc([session(site)]))
    seq = client.get(f"/api/works/{work}/trace", params={"agent": 1}).json()["seq"]
    push(node, work, doc([session(site, end=5)]))
    spans = client.get(f"/api/works/{work}/trace", params={"agent": 1, "after": seq}).json()["traces"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert [(s["name"], s["endTimeUnixNano"]) for s in spans] == [("agent.session", str(at(site, 5)))]


def test_wait_returns_as_soon_as_something_is_written(client, node, site):
    work, _, _ = site
    s = session(site)
    push(node, work, doc([s]))
    seq = client.get(f"/api/works/{work}/trace", params={"agent": 1}).json()["seq"]
    later = threading.Timer(0.3, lambda: push(node, work, doc([], [message(site, "u9", "来了", s["spanId"])])))
    later.start()
    t0 = time.monotonic()
    body = client.get(f"/api/works/{work}/trace", params={"agent": 1, "bodies": 1, "after": seq, "wait": 10}).json()
    later.join()
    assert time.monotonic() - t0 < 5
    assert [r["body"]["stringValue"] for r in body["logs"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]] == ["来了"]


def test_wait_gives_up_after_the_timeout_with_nothing_new(client, site):
    work, _, _ = site
    seq = client.get(f"/api/works/{work}/trace").json()["seq"]
    t0 = time.monotonic()
    body = client.get(f"/api/works/{work}/trace", params={"after": seq, "wait": 0.5}).json()
    assert 0.4 < time.monotonic() - t0 < 5 and body["seq"] == seq
    assert body["logs"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"] == []


def test_wait_ignores_changes_it_would_not_return(client, node, site):
    work, _, _ = site
    seq = client.get(f"/api/works/{work}/trace").json()["seq"]
    threading.Timer(0.2, lambda: push(node, work, doc([session(site)]))).start()        # agent 的段:默认读不到,不叫醒
    t0 = time.monotonic()
    client.get(f"/api/works/{work}/trace", params={"after": seq, "wait": 1})
    assert time.monotonic() - t0 > 0.9


def test_closing_ends_agent_spans_the_node_left_open(client, node, site, H):
    work, m, _ = site
    push(node, work, doc([session(site)]))                                                 # 没有节点来 flush(测试里没起)
    client.delete(f"/api/works/{work}/worklets/{m}", headers=H("bob"))
    [a] = [x for x in trace(client, work)[0] if x["name"] == "agent.session"]
    assert (a["memorytalk.end.reason"], a["status"], a["end"]) == ("detached", 1, at(site, 1))
