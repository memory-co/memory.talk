"""work_servers/bash_record —— bash:// 的每条命令进 trace:真 bash(带 rcfile)、真输入接口、测试进程里的节点。见 README.md。"""
import json
import time

import pytest

from memorytalk.node import layout
from memorytalk.node.node import Node
from tests._util import LocalCenter, LocalNodes, trace
from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def shell(client, home, svc, monkeypatch):
    node = Node(svc.runtime.node_dir, LocalCenter(svc.works))
    monkeypatch.setattr(svc.works, "nodes", LocalNodes(node))
    (home / "ws").mkdir(exist_ok=True)
    w = client.post("/api/works", json={"goal": "在终端里干活"}).json()
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    events = layout.hooks_file(svc.runtime.node_dir, m["id"])

    def count(kind):
        try:
            return sum(json.loads(l)["e"] == kind for l in events.read_text().splitlines())
        except FileNotFoundError:
            return 0

    def wait(kind, n, timeout=15):
        t0 = time.time()
        while time.time() - t0 < timeout and count(kind) < n:
            time.sleep(0.05)
        assert count(kind) >= n, f"等不到第 {n} 个 {kind}"
        node.poll()

    wait("start", 1)
    return w, m, node, count, wait


def send(client, w, m, **body):
    return client.post(f"/api/works/{w['id']}/worklets/{m['id']}/input", json={"kind": "text", **body})


def turns(client, w):
    spans, points = trace(client, w["id"])
    return [s for s in spans if s["name"] == "agent.turn"], [p for p in points if p["event"] == "agent.message"]


def test_a_command_becomes_a_turn_with_its_output(client, shell):
    w, m, node, count, wait = shell
    r = send(client, w, m, text="echo 记录里看得到")
    wait("done", count("done") + 1)
    [turn], messages = turns(client, w)
    assert [(p["memorytalk.message.role"], p["body"]) for p in messages] == [("user", "echo 记录里看得到"), ("assistant", "记录里看得到")]
    assert (turn["process.exit.code"], turn["memorytalk.end.reason"]) == (0, "completed")
    assert turn["memorytalk.input.id"] == r.json()["input_id"]                       # 从记录里送进去的那句,连上了这一轮
    [session] = [s for s in trace(client, w["id"])[0] if s["name"] == "agent.session"]
    assert session["memorytalk.agent"] == "bash" and turn["parentSpanId"] == session["spanId"]


def test_a_failing_command_keeps_its_exit_code(client, shell):
    w, m, node, count, wait = shell
    send(client, w, m, text="ls /definitely-not-here")
    wait("done", count("done") + 1)
    [turn], messages = turns(client, w)
    assert turn["process.exit.code"] == 2 and "definitely-not-here" in messages[-1]["body"]


def test_a_running_command_holds_input_until_forced(client, shell):
    w, m, node, count, wait = shell
    send(client, w, m, text="sleep 30")
    wait("cmd", count("cmd") + 1)                                                    # 命令开始了:状态 busy
    assert send(client, w, m, text="echo 插队").json()["error"] == "busy"
    assert client.post(f"/api/works/{w['id']}/worklets/{m['id']}/input", json={"kind": "keys", "keys": ["C-c"]}).status_code == 200
    wait("done", count("done") + 1)
    [turn], _ = turns(client, w)
    assert (turn["process.exit.code"], turn["memorytalk.end.reason"]) == (130, "cancelled")


def test_closing_flushes_and_ends_the_running_command(client, shell, svc):
    w, m, node, count, wait = shell
    send(client, w, m, text="sleep 30")
    wait("cmd", count("cmd") + 1)
    client.delete(f"/api/works/{w['id']}/worklets/{m['id']}")
    spans, _ = trace(client, w["id"])
    assert [(s["name"], s["memorytalk.end.reason"]) for s in spans if s["name"].startswith("agent.")] == \
        [("agent.session", "detached"), ("agent.turn", "detached")]
    assert not layout.worklet_dir(svc.runtime.node_dir, m["id"]).exists()


def test_a_script_is_not_recorded(client, home, svc):
    script = home / "ws" / "job.sh"
    script.parent.mkdir(exist_ok=True)
    script.write_text("sleep 30\n")
    w = client.post("/api/works", json={"goal": "跑个脚本"}).json()
    m = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{script}"}).json()
    assert m["handle"]["capabilities"] == ["input.text", "input.keys"]
    assert svc.work_servers.watch_spec("bash", m["id"], m["uri"]) is None


def test_a_shell_started_before_the_hooks_claims_no_record(client, shell, svc):
    w, m, node, count, wait = shell
    (layout.worklet_dir(svc.runtime.node_dir, m["id"]) / "bashrc").unlink()          # 当它是装钩子之前就起的老现场
    [listed] = client.get(f"/api/works/{w['id']}/worklets").json()
    assert "trace.agent" not in listed["handle"]["capabilities"]
