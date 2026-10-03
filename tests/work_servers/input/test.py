"""work_servers/input —— POST …/worklets/{w}/input:往现场里送字 / 按键;agent 忙的时候门控;trace 里留痕不留原文;连上它引起的那一轮。见 README.md。"""
import hashlib
import json
import os
import time

import pytest

from memorytalk.node import otlp
from tests._util import trace
from tests.conftest import needs_tmux

pytestmark = needs_tmux


def post(client, w, m, headers=None, **body):
    return client.post(f"/api/works/{w['id']}/worklets/{m['id']}/input", json=body, headers=headers)


@pytest.fixture
def bash(client, home):
    w = client.post("/api/works", json={"goal": "往终端里送"}).json()
    (home / "ws").mkdir(exist_ok=True)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    return w, m


@pytest.fixture
def claude(client, home, monkeypatch):
    """claude:// 现场(PATH 里是个假的 claude,一直跑着);agent 的状态由测试当节点推进 trace。"""
    bindir = home / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text("#!/bin/sh\nsleep 600\n")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    w = client.post("/api/works", json={"goal": "跟 agent 说话"}).json()
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"claude://{home / 'ws'}"}).json()
    return w, m


def node_push(svc, w, m, spans=(), records=()):
    """当节点推一批(进的是 POST /trace 的那个写入函数)。"""
    [seg] = [s for s in trace_spans(svc, w) if s["name"] == "worklet"]
    return svc.works.write_trace(w["id"], otlp.document([dict(s, traceId=seg["traceId"]) for s in spans],
                                                         [dict(r, traceId=seg["traceId"]) for r in records]), [])


def trace_spans(svc, w):
    d = svc.works.trace_of(w["id"], agent=True)
    return d.traces["resourceSpans"][0]["scopeSpans"][0]["spans"]


def session(svc, w, m):
    [seg] = [s for s in trace_spans(svc, w) if s["name"] == "worklet"]
    sid = otlp.session_span_id(m["id"], "s1", f"{m['id']}:u0")
    return sid, otlp.span(seg["traceId"], sid, seg["spanId"], "agent.session", int(seg["startTimeUnixNano"]) + 1,
                          {"memorytalk.worklet.id": m["id"], "gen_ai.conversation.id": "s1"})


def state(svc, w, m, value, n):
    sid, span = session(svc, w, m)
    node_push(svc, w, m, [span], [otlp.record("", sid, "agent.state", time.time_ns() + n, f"{m['id']}:state:{n}",
                                              {"memorytalk.worklet.id": m["id"], "memorytalk.state": value})])


def test_text_reaches_the_terminal(client, bash, home):
    w, m = bash
    marker = home / "ws" / "marker.txt"
    r = post(client, w, m, kind="text", text=f"echo 送到了 > {marker}")
    assert r.status_code == 200 and r.json()["state"] is None and len(r.json()["input_id"]) == 16
    for _ in range(100):
        if marker.exists() and marker.read_text().strip():
            break
        time.sleep(0.05)
    assert marker.read_text().strip() == "送到了"


def test_keys_are_pressed(client, bash):
    w, m = bash
    assert post(client, w, m, kind="keys", keys=["C-c"]).status_code == 200


def test_what_the_worklet_cannot_take_is_refused(client, bash):
    w, m = bash
    r = post(client, w, m, kind="paste", text="多行\n文字")
    assert r.status_code == 409 and r.json()["error"] == "unsupported"


def test_a_web_worklet_takes_no_input(client):
    w = client.post("/api/works", json={"goal": "网页"}).json()
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": "https://example.com"}).json()
    assert post(client, w, m, kind="text", text="hi").json()["error"] == "unsupported"


def test_no_site_no_input(client, bash, svc):
    w, m = bash
    svc.work_servers.destroy("bash", m["id"])
    r = post(client, w, m, kind="text", text="hi")
    assert r.status_code == 409 and r.json()["error"] == "gone"


def test_an_archived_work_takes_no_input(client, bash):
    w, m = bash
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    assert post(client, w, m, kind="text", text="hi").json()["error"] == "gone"


def test_text_is_capped_at_64_kib(client, bash):
    w, m = bash
    assert post(client, w, m, kind="text", text="x" * 65537, submit=False).status_code == 422


def test_unknown_worklet_is_404(client, bash):
    w, _ = bash
    assert post(client, w, {"id": f"{w['id']}-w9"}, kind="text", text="hi").status_code == 404


def test_each_input_is_a_point_without_the_text(client, bash, H):
    w, m = bash
    secret = "export TOKEN=s3cr3t-value"
    r = post(client, w, m, headers=H("bob"), kind="text", text=f"  {secret}\n", submit=False)
    _, points = trace(client, w["id"])
    [p] = [p for p in points if p["event"] == "worklet.input"]
    assert (p["user.id"], p["memorytalk.input.id"], p["memorytalk.input.kind"], p["memorytalk.input.length"]) == \
        ("bob", r.json()["input_id"], "text", len(secret) + 3)
    assert p["memorytalk.input.sha256"] == hashlib.sha256(secret.encode()).hexdigest()           # 指纹去掉首尾空白
    whole = client.get(f"/api/works/{w['id']}/trace", params={"agent": 1, "bodies": 1}).text
    assert "s3cr3t" not in whole                                                                 # 原文哪儿都没有


def test_a_busy_agent_needs_force(client, claude, svc):
    w, m = claude
    state(svc, w, m, "busy", 1)
    r = post(client, w, m, kind="text", text="插一句")
    assert r.status_code == 409 and r.json()["error"] == "busy"
    r = post(client, w, m, kind="text", text="插一句", force=True)
    assert r.status_code == 200 and r.json()["state"] == "busy"


def test_an_agent_waiting_for_approval_does_not_get_typed_into(client, claude, svc):
    w, m = claude
    state(svc, w, m, "blocked", 1)
    assert post(client, w, m, kind="text", text="好的").json()["error"] == "blocked"
    assert post(client, w, m, kind="keys", keys=["Escape"]).status_code == 200                   # 按键默认就是 force:能打断它


def test_an_idle_agent_takes_it(client, claude, svc):
    w, m = claude
    state(svc, w, m, "busy", 1)
    state(svc, w, m, "idle", 2)                                                                  # 看最新的那个状态
    r = post(client, w, m, kind="text", text="下一件事")
    assert r.status_code == 200 and r.json()["state"] == "idle"


def test_the_turn_it_starts_carries_the_input_id(client, claude, svc):
    w, m = claude
    input_id = post(client, w, m, kind="text", text="把配置改成环境变量").json()["input_id"]
    sid, span = session(svc, w, m)
    now = time.time_ns()

    def turn(uid, text):
        tid = otlp.turn_span_id(m["id"], f"{m['id']}:{uid}")
        return (otlp.span("", tid, sid, "agent.turn", now, {"memorytalk.worklet.id": m["id"]}),
                otlp.record("", tid, "agent.message", now, f"{m['id']}:{uid}",
                            {"memorytalk.worklet.id": m["id"], "memorytalk.message.role": "user"}, text))

    mine, typed = turn("u1", "把配置改成环境变量\n"), turn("u2", "这句是在终端窗里手打的")
    node_push(svc, w, m, [span, mine[0], typed[0]], [mine[1], typed[1]])
    turns = {s["spanId"]: s for s in trace(client, w["id"])[0] if s["name"] == "agent.turn"}
    assert turns[mine[0]["spanId"]]["memorytalk.input.id"] == input_id
    assert "memorytalk.input.id" not in turns[typed[0]["spanId"]]
