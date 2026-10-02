"""node/push —— 节点盯着工作单元、一轮一轮推给中心;推不成功重读,中心拒收跳过,flush / 现场没了收尾。见 README.md。"""
import json

import pytest

from memorytalk.node import claude, layout
from memorytalk.node.node import Node, Rejected

W, WORK, SID = "work_x-w1", "work_x", "11111111-2222-3333-4444-555555555555"
TRACE, PARENT, SOCK = "ab" * 16, "cd" * 8, "tmuxd-test"


class FakeCenter:
    """记下推上来的每一批,游标照中心那样存;fail = 接下来几次推不上去,reject = 接下来几次拒收。"""

    def __init__(self):
        self.pushes, self.saved, self.fail, self.reject = [], {}, 0, 0

    def push(self, work_id, body):
        if self.fail:
            self.fail -= 1
            raise ConnectionError("中心没起来")
        if self.reject:
            self.reject -= 1
            raise Rejected("422 不成形")
        self.pushes.append(body)
        for c in body["cursors"]:
            self.saved[(c["worklet_id"], c["source"])] = c["position"]
        return {}

    def cursors(self, work_id, worklet_id):
        return [{"worklet_id": w, "source": s, "position": p} for (w, s), p in self.saved.items() if w == worklet_id]

    def uids(self):
        return [kv["value"]["stringValue"] for b in self.pushes for rl in b["logs"]["resourceLogs"] for sl in rl["scopeLogs"]
                for r in sl["logRecords"] for kv in r["attributes"] if kv["key"] == "log.record.uid"]

    def spans(self):
        return [s for b in self.pushes for rs in b["traces"]["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]


@pytest.fixture
def env(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    (projects / "-proj").mkdir(parents=True)
    node_dir = tmp_path / "node"
    center = FakeCenter()
    node = Node(node_dir, center)
    alive = {SOCK: {W}}
    monkeypatch.setattr(Node, "_sessions", lambda self: alive)          # 不碰真 tmux:活着的会话由测试说了算
    monkeypatch.setattr(claude, "FIND_EVERY", 0)                         # 会话记录后出现:下一轮就找
    spec = {"work_id": WORK, "worklet_id": W, "trace_id": TRACE, "parent": PARENT, "server": "claude", "session_id": SID,
            "hooks": str(layout.hooks_file(node_dir, W)), "transcripts": str(projects), "tmux_socket": SOCK, "since": 1}
    transcript = projects / "-proj" / f"{SID}.jsonl"

    def write(*rows):
        with open(transcript, "a") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))

    return node, center, spec, write, alive, node_dir


def human(uuid, text, sec=1):
    return {"type": "user", "uuid": uuid, "timestamp": f"2026-10-02T11:00:0{sec}.000Z", "promptId": "p1",
            "message": {"role": "user", "content": text}}


def say(uuid, text, sec=2):
    return {"type": "assistant", "uuid": uuid, "timestamp": f"2026-10-02T11:00:0{sec}.000Z",
            "message": {"id": "m1", "role": "assistant", "stop_reason": None, "content": [{"type": "text", "text": text}]}}


def test_watching_reads_right_away_and_remembers_whom(env):
    node, center, spec, write, _, node_dir = env
    write(human("u1", "你好"))
    node.watch(spec)
    assert center.uids() == [f"{W}:u1", f"{W}:u1:state"]
    assert json.loads(layout.watch_file(node_dir, W).read_text())["worklet_id"] == W


def test_a_push_that_fails_is_read_again_next_time(env):
    node, center, spec, write, _, _ = env
    node.watch(spec)
    write(human("u1", "你好"))
    center.fail = 1
    node.poll()                                                          # 推不上去:游标不动
    assert center.uids() == []
    node.poll()
    assert center.uids() == [f"{W}:u1", f"{W}:u1:state"]                 # 同样的字节,同样的 uid


def test_a_rejected_batch_is_skipped_not_retried_forever(env):
    node, center, spec, write, _, _ = env
    node.watch(spec)
    write(human("u1", "一"))
    center.reject = 1
    node.poll()
    write(say("a1", "二"))
    node.poll()
    assert center.uids() == [f"{W}:a1:0"]


def test_the_cursor_is_pushed_with_the_data(env):
    node, center, spec, write, _, _ = env
    write(human("u1", "一"))
    node.watch(spec)
    assert center.saved[(W, SID)] == str(len(json.dumps(human("u1", "一"))) + 1)
    assert json.loads(center.saved[(W, "reader")])["turn"]["uid"] == f"{W}:u1"


def test_a_restarted_node_picks_up_where_the_center_says(env):
    node, center, spec, write, alive, node_dir = env
    write(human("u1", "一"))
    node.watch(spec)
    again = Node(node_dir, center)                                       # 节点重启:watch.json 还在,游标在中心
    again.load()
    write(say("a1", "二"))
    again.poll()
    assert center.uids() == [f"{W}:u1", f"{W}:u1:state", f"{W}:a1:0"]


def test_flush_reads_to_the_end_ends_what_is_open_and_stops_watching(env):
    node, center, spec, write, _, node_dir = env
    node.watch(spec)
    write(human("u1", "一"), say("a1", "二"))
    assert node.flush(W, "archived") == {"flushed": True, "watching": True}
    ended = {s["name"]: s for s in center.spans() if "endTimeUnixNano" in s}
    assert {n: next(kv["value"]["stringValue"] for kv in s["attributes"] if kv["key"] == "memorytalk.end.reason")
            for n, s in ended.items()} == {"agent.turn": "archived", "agent.session": "archived"}
    assert W not in node.watching and not layout.watch_file(node_dir, W).exists()
    assert layout.worklet_dir(node_dir, W).exists()                      # 归档还会回来:hooks 文件留着


def test_flush_for_a_closed_worklet_removes_its_directory(env):
    node, center, spec, write, _, node_dir = env
    node.watch(spec)
    node.flush(W, "detached")
    assert not layout.worklet_dir(node_dir, W).exists()


def test_a_vanished_site_ends_everything_as_gone(env):
    node, center, spec, write, alive, _ = env
    node.watch(spec)
    write(human("u1", "一"))
    alive[SOCK] = set()                                                  # tmux 会话没了
    node.poll()
    [worklet] = [s for s in center.spans() if s["name"] == "worklet"]
    assert (worklet["spanId"], worklet["status"]["code"]) == (PARENT, 0) and "endTimeUnixNano" in worklet
    ended = [s for s in center.spans() if s["name"].startswith("agent.") and "endTimeUnixNano" in s]
    assert {s["name"] for s in ended} == {"agent.turn", "agent.session"} and all(s["status"]["code"] == 0 for s in ended)
    assert W not in node.watching


def test_watching_again_with_a_new_worklet_span_starts_a_new_session(env):
    node, center, spec, write, _, _ = env
    write(human("u1", "一"))
    node.watch(spec)
    node.watch({**spec, "parent": "ef" * 8})                             # 重入开了新的 worklet 段
    write(human("u2", "二", sec=3))
    node.poll()
    sessions = {s["spanId"]: s.get("parentSpanId") for s in center.spans() if s["name"] == "agent.session"}
    assert sorted(sessions.values()) == sorted([PARENT, "ef" * 8])


def test_list_says_whom_it_watches(env):
    node, _, spec, _, _, _ = env
    node.watch(spec)
    assert node.list() == {"watching": [W], "sessions": {SOCK: [W]}}
