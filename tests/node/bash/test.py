"""node/bash —— 节点读 bash 的命令事件:一条命令一轮,人那句 = 命令,回复 = 输出。见 README.md。"""
import hashlib
import json

import pytest

from memorytalk.node import bash as bash_mod
from memorytalk.node.base import Spec
from memorytalk.node.bash import BashReader

W, TRACE, PARENT = "work_x-w2", "ab" * 16, "cd" * 8
S = 1_000_000_000
T0 = 1_790_000_000 * S


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.fixture
def env(tmp_path):
    events = tmp_path / "hooks.jsonl"
    outdir = tmp_path / "out"
    outdir.mkdir()

    class Env:
        spec = Spec(work_id="work_x", worklet_id=W, trace_id=TRACE, parent=PARENT, hooks=str(events), server="bash")

        @staticmethod
        def emit(*rows):
            with open(events, "a") as f:
                f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

        @staticmethod
        def output(name, text):
            path = outdir / name
            path.write_text(text)
            return str(path)

        @staticmethod
        def offset_of(n):
            """第 n 行(从 0 数)在事件文件里从哪个字节开始:uid 用它。"""
            lines = events.read_bytes().split(b"\n")
            return sum(len(l) + 1 for l in lines[:n])

    return Env


def start(sec=0, pid=4242):
    return {"e": "start", "ts": T0 + sec * S, "pid": pid, "cwd": "/w", "bash": "5.2.15(1)-release"}


def cmd(sec, text, hidden=False, cwd="/w"):
    return {"e": "cmd", "ts": T0 + int(sec * S), "cmd": "" if hidden else text, "cwd": cwd, "hidden": hidden}


def done(sec, code=0, out="", cwd="/w"):
    return {"e": "done", "ts": T0 + int(sec * S), "code": code, "cwd": cwd, "out": out}


def attrs(kvs):
    return {kv["key"]: int(kv["value"]["intValue"]) if "intValue" in kv["value"] else next(iter(kv["value"].values())) for kv in kvs}


def flat(batch):
    spans = {}
    for s in batch.spans.values():
        spans.setdefault(s["name"], []).append({"id": s["spanId"], "parent": s.get("parentSpanId"), "start": int(s["startTimeUnixNano"]),
                                                "end": int(s["endTimeUnixNano"]) if "endTimeUnixNano" in s else None,
                                                "status": s["status"]["code"], **attrs(s["attributes"])})
    points = [{"event": r["eventName"], "span": r.get("spanId"), "time": int(r["timeUnixNano"]),
               "body": r.get("body", {}).get("stringValue"), **attrs(r["attributes"])} for r in batch.records]
    return spans, points


def step(r, **kw):
    b = r.step(**kw)
    r.commit(b)
    return b


def test_a_command_is_a_turn_and_its_output_the_reply(env):
    env.emit(start(), cmd(1, "git status"), done(1.5, out=env.output("1.txt", "On branch main\nnothing to commit\n\n")))
    spans, points = flat(step(BashReader(env.spec)))
    [seg], [turn] = spans["agent.session"], spans["agent.turn"]
    assert seg["id"] == sha(f"memorytalk/span/session/{W}/bash:4242/{W}:hook:0") and seg["parent"] == PARENT
    assert (seg["memorytalk.agent"], seg["process.pid"], seg["end"]) == ("bash", 4242, None)
    uid = f"{W}:hook:{env.offset_of(1)}"
    assert turn["id"] == sha(f"memorytalk/span/turn/{W}/{uid}") and turn["parent"] == seg["id"]
    assert (turn["start"], turn["end"], turn["process.exit.code"], turn["memorytalk.end.reason"]) == (T0 + S, T0 + 3 * S // 2, 0, "completed")
    talk = [(p["memorytalk.message.role"], p["memorytalk.message.kind"], p["body"], p["span"]) for p in points if p["event"] == "agent.message"]
    assert talk == [("user", "text", "git status", turn["id"]), ("assistant", "output", "On branch main\nnothing to commit", turn["id"])]
    assert [p["memorytalk.state"] for p in points if p["event"] == "agent.state"] == ["idle", "busy", "idle"]


def test_a_failing_command_keeps_its_exit_code(env):
    env.emit(start(), cmd(1, "ls /nope"), done(1.1, code=2, out=env.output("1.txt", "ls: cannot access '/nope'\n")))
    spans, _ = flat(step(BashReader(env.spec)))
    assert (spans["agent.turn"][0]["process.exit.code"], spans["agent.turn"][0]["status"]) == (2, 1)


def test_ctrl_c_cancels_the_turn(env):
    env.emit(start(), cmd(1, "sleep 100"), done(3, code=130, out=env.output("1.txt", "^C\n")))
    spans, _ = flat(step(BashReader(env.spec)))
    assert spans["agent.turn"][0]["memorytalk.end.reason"] == "cancelled"


def test_a_command_with_no_output_has_no_reply(env):
    env.emit(start(), cmd(1, "cd /tmp"), done(1.1, cwd="/tmp"))
    spans, points = flat(step(BashReader(env.spec)))
    assert [p["memorytalk.message.role"] for p in points if p["event"] == "agent.message"] == ["user"]
    assert (spans["agent.turn"][0]["memorytalk.shell.cwd"], spans["agent.turn"][0]["memorytalk.end.shell.cwd"]) == ("/w", "/tmp")


def test_a_hidden_command_records_neither_text_nor_output(env):
    env.emit(start(), cmd(1, "export TOKEN=x", hidden=True), done(1.1))
    _, points = flat(step(BashReader(env.spec)))
    [msg] = [p for p in points if p["event"] == "agent.message"]
    assert (msg["body"], msg["memorytalk.message.hidden"]) == ("", True)


def test_a_running_command_is_an_open_turn(env):
    env.emit(start(), cmd(1, "make"))
    spans, points = flat(step(BashReader(env.spec)))
    assert spans["agent.turn"][0]["end"] is None and [p["memorytalk.state"] for p in points if p["event"] == "agent.state"][-1] == "busy"


def test_long_output_keeps_head_and_tail(env, monkeypatch):
    monkeypatch.setattr(bash_mod, "OUTPUT_LIMIT", 100)
    monkeypatch.setattr(bash_mod, "OUTPUT_HEAD", 20)
    text = "".join(f"line {i:04d}\n" for i in range(300))
    env.emit(start(), cmd(1, "seq"), done(2, out=env.output("1.txt", text)))
    _, points = flat(step(BashReader(env.spec)))
    [out] = [p["body"] for p in points if p.get("memorytalk.message.kind") == "output"]
    assert out.startswith("line 0000\nline 0001") and out.endswith("line 0299") and "中间省略" in out


def test_output_files_are_removed_once_pushed(env):
    path = env.output("1.txt", "hi\n")
    env.emit(start(), cmd(1, "echo hi"), done(1.1, out=path))
    r = BashReader(env.spec)
    b = r.step()
    assert open(path).read() == "hi\n"                                            # 推之前还在(推不上去要重读)
    r.commit(b)
    assert not __import__("os").path.exists(path)


def test_a_new_shell_replaces_the_session(env):
    env.emit(start(), cmd(1, "exec bash"), start(2, pid=5000))
    spans, _ = flat(step(BashReader(env.spec)))
    first, second = sorted(spans["agent.session"], key=lambda s: s["start"])
    assert (first["memorytalk.end.reason"], second["process.pid"], second["end"]) == ("replaced", 5000, None)
    assert spans["agent.turn"][0]["memorytalk.end.reason"] == "cancelled"        # exec 掉的那条没等到 done


def test_reading_resumes_from_the_saved_cursor(env):
    env.emit(start(), cmd(1, "make"))
    first = step(BashReader(env.spec))
    again = BashReader.restored(env.spec, first.cursors(W))
    env.emit(done(5, out=env.output("1.txt", "built\n")))
    spans, points = flat(step(again))
    assert [p["body"] for p in points if p["event"] == "agent.message"] == ["built"]
    assert spans["agent.turn"][0]["end"] == T0 + 5 * S


def test_finish_ends_a_running_command_and_the_session(env):
    env.emit(start(), cmd(1, "sleep 1000"))
    r = BashReader(env.spec)
    step(r)
    spans, _ = flat(step(r, finish=("gone", 0)))
    assert [(s["memorytalk.end.reason"], s["status"]) for s in spans["agent.turn"] + spans["agent.session"]] == [("gone", 0), ("gone", 0)]
