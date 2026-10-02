"""work_servers/claude_worklet —— claude:// 开起来就定身份(--session-id + hooks),它的 output 由节点推进 trace。见 README.md。"""
import json
import os
import subprocess
import sys
import time
import uuid

import pytest

from memorytalk.node import claude as reader_mod
from memorytalk.node import layout
from memorytalk.node.node import Node
from tests._util import LocalCenter, LocalNodes, trace
from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def fake_claude(home, monkeypatch):
    """PATH 里的假 claude:把参数记下来(一次一段),然后一直跑着。"""
    bindir = home / "bin"
    bindir.mkdir()
    log = home / "claude-argv"
    fake = bindir / "claude"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' --- \"$@\" >> {log}\nsleep 600\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")

    def launches(at_least=1):
        blocks = []
        for _ in range(100):                                  # tmux 里的 sh 起来要一会儿
            blocks = log.read_text().split("---\n")[1:] if log.exists() else []
            if len(blocks) >= at_least and blocks[-1].endswith("\n"):
                break
            time.sleep(0.05)
        return [b.splitlines() for b in blocks]

    return launches


def arg(argv, flag):
    return argv[argv.index(flag) + 1]


@pytest.fixture
def opened(client, home, fake_claude):
    w = client.post("/api/works", json={"goal": "让 claude 干活"}).json()
    proj = home / "ws" / "proj"
    proj.mkdir(parents=True)
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"claude://{proj}"}).json()
    return w, m, fake_claude()[-1]


@pytest.fixture
def node(svc, home, monkeypatch):
    """节点放在测试进程里:中心让它 watch / flush,它推的进 WorkService.write_trace。"""
    monkeypatch.setattr(reader_mod, "FIND_EVERY", 0)
    n = Node(svc.runtime.node_dir, LocalCenter(svc.works))
    monkeypatch.setattr(svc.works, "nodes", LocalNodes(n))
    return n


def test_claude_starts_with_a_pinned_session_and_injected_hooks(opened, svc):
    _, m, argv = opened
    session = arg(argv, "--session-id")
    assert str(uuid.UUID(session)) == session
    settings = json.loads(open(arg(argv, "--settings")).read())
    assert set(settings["hooks"]) >= {"SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "Notification"}
    command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert str(layout.HOOK_SCRIPT) in command and str(layout.hooks_file(svc.runtime.node_dir, m["id"])) in command


def test_the_session_id_is_kept_in_the_registry_not_in_the_api(client, opened, svc):
    w, m, argv = opened
    assert svc.works.worklets.get(w["id"], m["id"]).session_id == arg(argv, "--session-id")
    assert "session_id" not in m and "session_id" not in client.get(f"/api/works/{w['id']}/worklets").json()[0]


def test_its_output_is_the_trace_not_rounds(client, opened):
    w, m, _ = opened
    assert m["handle"]["capabilities"] == ["send", "trace.agent"]
    assert client.get(f"/api/works/{w['id']}/worklets/{m['id']}/rounds").json() == []


def test_reattaching_a_live_site_does_not_start_claude_again(client, opened, fake_claude):
    w, m, _ = opened
    client.post(f"/api/works/{w['id']}/worklets/{m['id']}/attach")
    assert len(fake_claude()) == 1


def test_reattaching_after_the_site_died_starts_a_new_session(client, opened, svc, fake_claude):
    w, m, argv = opened
    svc.work_servers.destroy("claude", m["id"])
    client.post(f"/api/works/{w['id']}/worklets/{m['id']}/attach")
    again = fake_claude(2)[-1]
    assert arg(again, "--session-id") != arg(argv, "--session-id")
    assert svc.works.worklets.get(w["id"], m["id"]).session_id == arg(again, "--session-id")


def test_the_hook_script_appends_one_line_with_the_time_it_got_the_event(tmp_path):
    out = tmp_path / "hooks.jsonl"
    for event in ("SessionStart", "Stop"):
        r = subprocess.run([sys.executable, str(layout.HOOK_SCRIPT), str(out)], input=json.dumps({"hook_event_name": event}),
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == ""                              # 什么都不往 stdout 写(会进 agent 的上下文)
    lines = [json.loads(l) for l in out.read_text().splitlines()]
    assert [l["hook_event_name"] for l in lines] == ["SessionStart", "Stop"] and all(isinstance(l["_ts"], int) for l in lines)


# ---- 节点:开起来就盯上,claude 写什么推什么 ----

def write_session(svc, home, w, m, argv):
    """照 claude 的样子写:hook 报会话开始和一轮的起止,会话记录里一问一答。"""
    sid = arg(argv, "--session-id")
    path = home / "claude" / "-proj" / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time_ns()
    hooks = layout.hooks_file(svc.runtime.node_dir, m["id"])
    stamp = lambda ns: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ns / 1e9)) + f".{ns // 1_000_000 % 1000:03d}Z"
    with open(hooks, "a") as f:
        f.write(json.dumps({"session_id": sid, "hook_event_name": "SessionStart", "source": "startup",
                            "transcript_path": str(path), "_ts": now}) + "\n")
    with open(path, "a") as f:
        f.write(json.dumps({"type": "user", "uuid": "u1", "timestamp": stamp(now + 10**9), "promptId": "p1",
                            "message": {"role": "user", "content": "把配置改成环境变量"}}) + "\n")
        f.write(json.dumps({"type": "assistant", "uuid": "a1", "timestamp": stamp(now + 2 * 10**9),
                            "message": {"id": "m1", "role": "assistant", "stop_reason": "end_turn",
                                        "usage": {"input_tokens": 3, "output_tokens": 4},
                                        "content": [{"type": "text", "text": "改好了"}]}}) + "\n")
    with open(hooks, "a") as f:
        f.write(json.dumps({"session_id": sid, "hook_event_name": "Stop", "prompt_id": "p1", "_ts": now + 3 * 10**9}) + "\n")


@pytest.fixture
def watched(client, home, node, fake_claude):
    w = client.post("/api/works", json={"goal": "让 claude 干活"}).json()
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"claude://{home / 'ws'}"}).json()
    return w, m, fake_claude()[-1]


def test_opening_it_makes_the_node_watch_under_the_worklet_span(client, watched, node, svc):
    w, m, argv = watched
    spec = node.watching[m["id"]].spec
    [seg] = [s for s in trace(client, w["id"])[0] if s["name"] == "worklet"]
    assert (spec.parent, spec.trace_id, spec.session_id, spec.tmux_socket) == \
        (seg["spanId"], seg["traceId"], arg(argv, "--session-id"), svc.work_servers.tmuxd.tmux_socket)


def test_what_claude_writes_ends_up_in_the_trace(client, watched, node, svc, home):
    w, m, argv = watched
    write_session(svc, home, w, m, argv)
    node.poll()
    spans, points = trace(client, w["id"])
    [seg] = [s for s in spans if s["name"] == "worklet"]
    [session] = [s for s in spans if s["name"] == "agent.session"]
    [turn] = [s for s in spans if s["name"] == "agent.turn"]
    assert session["parentSpanId"] == seg["spanId"] and turn["parentSpanId"] == session["spanId"]
    assert (turn["memorytalk.end.reason"], turn["gen_ai.usage.input_tokens"], turn["gen_ai.usage.output_tokens"]) == ("completed", 3, 4)
    talk = [(p["memorytalk.message.role"], p["body"]) for p in points if p["event"] == "agent.message"]
    assert talk == [("user", "把配置改成环境变量"), ("assistant", "改好了")]
    assert svc.works.cursors(w["id"], m["id"]).cursors                                  # 推到哪了存在中心


def test_closing_flushes_and_ends_the_session_as_detached(client, watched, node, svc, home, H):
    w, m, argv = watched
    write_session(svc, home, w, m, argv)                                                  # 还没轮到节点读,就关了
    client.delete(f"/api/works/{w['id']}/worklets/{m['id']}", headers=H("bob"))
    spans, points = trace(client, w["id"])
    [session] = [s for s in spans if s["name"] == "agent.session"]
    assert session["memorytalk.end.reason"] == "detached" and len([p for p in points if p["event"] == "agent.message"]) == 2
    assert m["id"] not in node.watching and not layout.worklet_dir(svc.runtime.node_dir, m["id"]).exists()


def test_archiving_flushes_with_reason_archived(client, watched, node, svc, home):
    w, m, argv = watched
    write_session(svc, home, w, m, argv)
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    [session] = [s for s in trace(client, w["id"])[0] if s["name"] == "agent.session"]
    assert session["memorytalk.end.reason"] == "archived" and m["id"] not in node.watching


def test_when_the_site_dies_the_node_reports_gone(client, watched, node, svc, home):
    w, m, argv = watched
    write_session(svc, home, w, m, argv)
    node.poll()
    svc.work_servers.destroy("claude", m["id"])                                           # claude 自己退出了
    node.poll()
    spans, _ = trace(client, w["id"])
    [seg] = [s for s in spans if s["name"] == "worklet"]
    [session] = [s for s in spans if s["name"] == "agent.session"]
    assert (seg["memorytalk.end.reason"], seg["status"]) == ("gone", 0) and "memorytalk.end.user.id" not in seg
    assert (session["memorytalk.end.reason"], session["status"]) == ("gone", 0)
    assert m["id"] not in node.watching


def test_reattaching_after_gone_watches_the_new_worklet_span(client, watched, node, svc, home):
    w, m, argv = watched
    svc.work_servers.destroy("claude", m["id"])
    node.poll()
    client.post(f"/api/works/{w['id']}/worklets/{m['id']}/attach")
    segs = [s for s in trace(client, w["id"])[0] if s["name"] == "worklet"]
    assert len(segs) == 2 and node.watching[m["id"]].spec.parent == segs[-1]["spanId"]


def test_the_center_coming_back_asks_the_node_to_watch_live_sites(watched, node, svc):
    w, m, _ = watched
    node.watching.clear()
    assert svc.works.reconcile() == 1 and m["id"] in node.watching
