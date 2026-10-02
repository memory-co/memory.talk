"""node/claude —— 节点读 Claude Code 的会话记录和 hooks,切成会话 / 轮次 / 工具段、消息点、状态点。见 README.md。"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from memorytalk.node import claude as reader_mod
from memorytalk.node.claude import ClaudeReader, Spec, restore

W = "work_x-w1"
SID, SID2 = "11111111-2222-3333-4444-555555555555", "66666666-7777-8888-9999-000000000000"
TRACE, PARENT = "ab" * 16, "cd" * 8
BASE = datetime(2026, 10, 2, 11, 0, 0, tzinfo=timezone.utc)


def ts(sec: float) -> str:
    return (BASE + timedelta(seconds=sec)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ns(sec: float) -> int:
    return int(BASE.timestamp()) * 1_000_000_000 + int(round(sec * 1000)) * 1_000_000


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---- 会话记录和 hook 事件,照 Claude Code 2.1 真实记录的样子造 ----

def human(uuid, sec, text, prompt, sid=SID, **kw):
    return {"type": "user", "uuid": uuid, "timestamp": ts(sec), "promptId": prompt, "sessionId": sid, "isSidechain": False,
            "origin": {"kind": "human"}, "message": {"role": "user", "content": text}, **kw}


def assistant(uuid, sec, blocks, mid, stop="end_turn", usage=(2, 5, 100, 1000), sid=SID):
    u = dict(zip(("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"), usage))
    return {"type": "assistant", "uuid": uuid, "timestamp": ts(sec), "sessionId": sid, "isSidechain": False,
            "message": {"id": mid, "role": "assistant", "stop_reason": stop, "usage": u, "content": blocks}}


def say(uuid, sec, text, mid, **kw):
    return assistant(uuid, sec, [{"type": "text", "text": text}], mid, **kw)


def call(uuid, sec, tool_id, name, inp, mid, **kw):
    return assistant(uuid, sec, [{"type": "tool_use", "id": tool_id, "name": name, "input": inp}], mid, stop="tool_use", **kw)


def result(uuid, sec, tool_id, out, prompt, error=False, sid=SID):
    return {"type": "user", "uuid": uuid, "timestamp": ts(sec), "promptId": prompt, "sessionId": sid, "isSidechain": False,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": out, "is_error": error}]}}


def interrupt(uuid, sec, prompt):
    return {"type": "user", "uuid": uuid, "timestamp": ts(sec), "promptId": prompt, "sessionId": SID, "isSidechain": False,
            "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}}


def hook(event, sec, sid=SID, **kw):
    return {"session_id": sid, "hook_event_name": event, "_ts": ns(sec), **kw}


@pytest.fixture
def env(tmp_path):
    projects = tmp_path / "projects"
    (projects / "-proj").mkdir(parents=True)
    hooks_path = tmp_path / "hooks.jsonl"

    class Env:
        spec = Spec(work_id="work_x", worklet_id=W, trace_id=TRACE, parent=PARENT, hooks=str(hooks_path),
                    transcripts=str(projects), session_id=SID)

        @staticmethod
        def transcript(sid=SID):
            return projects / "-proj" / f"{sid}.jsonl"

        @staticmethod
        def write(rows, sid=SID):
            with open(Env.transcript(sid), "a") as f:
                f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

        @staticmethod
        def hooks(rows):
            with open(hooks_path, "a") as f:
                f.write("".join(json.dumps(r) + "\n" for r in rows))

        @staticmethod
        def start(sid=SID, sec=0, source="startup"):
            Env.hooks([hook("SessionStart", sec, sid=sid, source=source, transcript_path=str(Env.transcript(sid)))])

    return Env


def attrs(kvs):
    return {kv["key"]: int(kv["value"]["intValue"]) if "intValue" in kv["value"] else next(iter(kv["value"].values())) for kv in kvs}


def flat(batch):
    """一批拍平:段按名字分组(属性展开),点一行一个(event / span / uid / body + 属性)。"""
    spans = {}
    for s in batch.spans.values():
        spans.setdefault(s["name"], []).append({"id": s["spanId"], "parent": s.get("parentSpanId"), "start": int(s["startTimeUnixNano"]),
                                                "end": int(s["endTimeUnixNano"]) if "endTimeUnixNano" in s else None,
                                                "status": s["status"]["code"], "links": [l["spanId"] for l in s["links"]],
                                                **attrs(s["attributes"])})
    points = [{"event": r["eventName"], "span": r.get("spanId"), "time": int(r["timeUnixNano"]),
               "body": r.get("body", {}).get("stringValue"), **attrs(r["attributes"])} for r in batch.records]
    return spans, points


def step(r, **kw):
    b = r.step(**kw)
    r.commit(b)
    return b


def one_turn(env):
    env.start()
    env.hooks([hook("UserPromptSubmit", 0.9, prompt_id="p1")])
    env.write([human("u1", 1, "把配置改成环境变量", "p1"),
               call("a1", 2, "toolu_1", "Edit", {"file": "config.py"}, "m1"),
               result("r1", 3, "toolu_1", "ok", "p1"),
               say("a2", 4, "改好了", "m2")])
    env.hooks([hook("Stop", 4.5, prompt_id="p1")])


def test_one_turn_runs_from_the_human_input_to_the_stop_hook(env):
    one_turn(env)
    spans, _ = flat(step(ClaudeReader(env.spec)))
    [seg], [turn], [tool] = spans["agent.session"], spans["agent.turn"], spans["agent.tool"]
    assert seg["id"] == sha(f"memorytalk/span/session/{W}/{SID}/{W}:hook:0") and seg["parent"] == PARENT
    assert (seg["end"], seg["memorytalk.session.source"], seg["gen_ai.conversation.id"]) == (None, "startup", SID)
    assert turn["id"] == sha(f"memorytalk/span/turn/{W}/{W}:u1") and turn["parent"] == seg["id"]
    assert (turn["start"], turn["end"], turn["status"], turn["memorytalk.end.reason"]) == (ns(1), ns(4.5), 1, "completed")
    assert tool["id"] == sha(f"memorytalk/span/tool/{W}/toolu_1") and tool["parent"] == turn["id"]
    assert (tool["start"], tool["end"], tool["status"], tool["gen_ai.tool.name"]) == (ns(2), ns(3), 1, "Edit")


def test_every_message_is_a_point_with_a_stable_uid(env):
    one_turn(env)
    spans, points = flat(step(ClaudeReader(env.spec)))
    turn, tool = spans["agent.turn"][0]["id"], spans["agent.tool"][0]["id"]
    talk = [(p["event"], p["span"], p["log.record.uid"], p.get("memorytalk.message.role"), p["body"]) for p in points
            if p["event"] != "agent.state"]
    assert talk == [("agent.message", turn, f"{W}:u1", "user", "把配置改成环境变量"),
                    ("agent.tool.input", tool, f"{W}:a1:0", None, '{"file": "config.py"}'),
                    ("agent.tool.output", tool, f"{W}:r1:0", None, "ok"),
                    ("agent.message", turn, f"{W}:a2:0", "assistant", "改好了")]
    assert all(p["memorytalk.worklet.id"] == W for p in points)
    assert spans["agent.turn"][0]["memorytalk.message.count"] == 2


def test_state_follows_the_hooks(env):
    one_turn(env)
    _, points = flat(step(ClaudeReader(env.spec)))
    seg = sha(f"memorytalk/span/session/{W}/{SID}/{W}:hook:0")
    assert [(p["memorytalk.state"], p["span"]) for p in points if p["event"] == "agent.state"] == \
        [("idle", seg), ("busy", seg), ("idle", seg)]


def test_reading_again_with_nothing_new_gives_nothing(env):
    one_turn(env)
    r = ClaudeReader(env.spec)
    step(r)
    b = r.step()
    assert b.empty() and b.state == r.state and b.drained


def test_without_hooks_end_turn_closes_the_turn(env):
    env.write([human("u1", 1, "hi", "p1"), say("a1", 2, "hello", "m1")])
    spans, points = flat(step(ClaudeReader(env.spec)))
    [seg], [turn] = spans["agent.session"], spans["agent.turn"]
    assert seg["id"] == sha(f"memorytalk/span/session/{W}/{SID}/{W}:u1")        # 没有 SessionStart:第一条记录开会话段
    assert (turn["end"], turn["memorytalk.end.reason"]) == (ns(2), "completed")
    assert [p["memorytalk.state"] for p in points if p["event"] == "agent.state"] == ["busy", "idle"]


def test_turn_duration_closes_the_turn_when_hooks_are_on(env):
    env.start()
    env.write([human("u1", 1, "hi", "p1"), say("a1", 2, "hello", "m1"),
               {"type": "system", "subtype": "turn_duration", "uuid": "d1", "timestamp": ts(2.5), "durationMs": 1500}])
    spans, _ = flat(step(ClaudeReader(env.spec)))
    assert (spans["agent.turn"][0]["end"], spans["agent.turn"][0]["memorytalk.end.reason"]) == (ns(2.5), "completed")


def test_with_hooks_end_turn_alone_does_not_close_the_turn(env):
    env.start()
    env.write([human("u1", 1, "hi", "p1"), say("a1", 2, "hello", "m1")])
    spans, _ = flat(step(ClaudeReader(env.spec)))
    assert spans["agent.turn"][0]["end"] is None                                 # 等 Stop(或 turn_duration)


def test_esc_cancels_the_turn_and_its_open_tool(env):
    env.start()
    env.write([human("u1", 1, "跑一下测试", "p1"), call("a1", 2, "toolu_1", "Bash", {"command": "pytest"}, "m1"),
               interrupt("i1", 5, "p1")])
    spans, points = flat(step(ClaudeReader(env.spec)))
    [turn], [tool] = spans["agent.turn"], spans["agent.tool"]
    assert (turn["end"], turn["memorytalk.end.reason"], turn["status"]) == (ns(5), "cancelled", 1)
    assert (tool["end"], tool["memorytalk.end.reason"]) == (ns(5), "cancelled")
    assert ("system", "[Request interrupted by user]") in [(p.get("memorytalk.message.role"), p["body"]) for p in points]
    assert [p["memorytalk.state"] for p in points if p["event"] == "agent.state"][-1] == "idle"


def test_clear_replaces_the_session(env):
    one_turn(env)
    env.hooks([hook("SessionEnd", 10, reason="clear"), hook("SessionStart", 10.1, sid=SID2, source="clear",
                                                             transcript_path=str(env.transcript(SID2)))])
    env.write([{"type": "user", "uuid": "c1", "timestamp": ts(10.05), "sessionId": SID2, "isSidechain": False,
                "message": {"role": "user", "content": "<command-name>/clear</command-name>"}},
               human("u2", 12, "下一件事", "p2", sid=SID2)], sid=SID2)
    spans, points = flat(step(ClaudeReader(env.spec)))
    first, second = sorted(spans["agent.session"], key=lambda s: s["start"])
    assert (first["end"], first["memorytalk.end.reason"]) == (ns(10), "replaced")
    assert (second["gen_ai.conversation.id"], second["memorytalk.session.source"], second["end"]) == (SID2, "clear", None)
    clear = next(p for p in points if p["log.record.uid"] == f"{W}:c1")
    assert (clear["memorytalk.message.role"], clear["span"]) == ("system", second["id"])           # 本地命令不开轮次
    [t2] = [t for t in spans["agent.turn"] if t["memorytalk.message.count"] and t["start"] == ns(12)]
    assert t2["parent"] == second["id"] and t2["end"] is None


def test_a_stop_for_an_earlier_prompt_does_not_end_the_next_turn(env):
    env.start()
    env.write([human("u1", 1, "一", "p1"), say("a1", 2, "好", "m1"), human("u2", 3, "二", "p2")])
    env.hooks([hook("Stop", 3.5, prompt_id="p1")])
    spans, _ = flat(step(ClaudeReader(env.spec)))
    first, second = sorted(spans["agent.turn"], key=lambda t: t["start"])
    assert (first["end"], first["memorytalk.end.reason"]) == (ns(2), "completed")    # 人又说了一句:上一轮按它最后一条收
    assert second["end"] is None


def test_a_failed_tool_call_is_an_error_span(env):
    env.start()
    env.write([human("u1", 1, "x", "p1"), call("a1", 2, "toolu_1", "Bash", {"command": "sleep 30"}, "m1"),
               result("r1", 2.1, "toolu_1", "<tool_use_error>Blocked</tool_use_error>", "p1", error=True)])
    spans, points = flat(step(ClaudeReader(env.spec)))
    assert spans["agent.tool"][0]["status"] == 2
    [out] = [p for p in points if p["event"] == "agent.tool.output"]
    assert out["memorytalk.tool.error"] is True and out["gen_ai.tool.call.id"] == "toolu_1"


def test_tokens_are_summed_once_per_api_message(env):
    env.start()
    thinking = assistant("a1", 2, [{"type": "thinking", "thinking": "想想", "signature": "x"}], "m1", stop="end_turn")
    env.write([human("u1", 1, "x", "p1"), thinking, say("a2", 2.1, "好", "m1"), say("a3", 3, "还有", "m2", usage=(1, 1, 0, 10))])
    spans, points = flat(step(ClaudeReader(env.spec)))
    turn = spans["agent.turn"][0]
    assert (turn["gen_ai.usage.input_tokens"], turn["gen_ai.usage.output_tokens"]) == (1113, 6)   # m1 一次(2+100+1000)+ m2(1+0+10)
    assert (turn["gen_ai.usage.cache_read.input_tokens"], turn["gen_ai.usage.cache_creation.input_tokens"]) == (1010, 100)
    assert [p["memorytalk.message.kind"] for p in points if p["event"] == "agent.message"] == ["text", "thinking", "text", "text"]


def test_a_permission_prompt_blocks_until_the_tool_runs(env):
    env.start()
    env.hooks([hook("UserPromptSubmit", 0.9, prompt_id="p1"),
               hook("Notification", 2.5, notification_type="permission_prompt", message="Claude needs your permission to use Bash"),
               hook("PreToolUse", 4, prompt_id="p1", tool_name="Bash"), hook("Stop", 6, prompt_id="p1")])
    env.write([human("u1", 1, "x", "p1"), call("a1", 2, "toolu_1", "Bash", {"command": "ls"}, "m1"),
               result("r1", 4.5, "toolu_1", "a b", "p1"), say("a2", 5, "好了", "m2")])
    _, points = flat(step(ClaudeReader(env.spec)))
    assert [p["memorytalk.state"] for p in points if p["event"] == "agent.state"] == ["idle", "busy", "blocked", "busy", "idle"]


def test_a_task_notification_is_a_turn_started_by_the_system(env):
    env.start()
    env.write([human("t1", 1, "<task-notification>…</task-notification>", "p9", origin={"kind": "task-notification"},
                     promptSource="system", turnOrigin="task_notification")])
    spans, points = flat(step(ClaudeReader(env.spec)))
    assert spans["agent.turn"][0]["memorytalk.turn.origin"] == "task-notification"
    assert [p["memorytalk.message.role"] for p in points if p["event"] == "agent.message"] == ["system"]


def test_reading_resumes_from_the_saved_cursor(env):
    env.start()
    env.write([human("u1", 1, "一", "p1"), call("a1", 2, "toolu_1", "Read", {"f": "a"}, "m1")])
    r = ClaudeReader(env.spec)
    first = step(r)
    again = ClaudeReader(env.spec, restore(env.spec, first.cursors(W)))          # 节点重启:从中心存的游标接着读
    env.write([result("r1", 3, "toolu_1", "内容", "p1"), say("a2", 4, "读完了", "m2")])
    env.hooks([hook("Stop", 4.5, prompt_id="p1")])
    spans, points = flat(step(again))
    assert [p["log.record.uid"] for p in points if p["event"] != "agent.state"] == [f"{W}:r1:0", f"{W}:a2:0"]
    assert spans["agent.tool"][0]["end"] == ns(3) and spans["agent.turn"][0]["end"] == ns(4.5)
    assert spans["agent.turn"][0]["id"] == sha(f"memorytalk/span/turn/{W}/{W}:u1")


def test_cursors_say_how_far_each_source_was_read(env):
    one_turn(env)
    b = step(ClaudeReader(env.spec))
    rows = {c["source"]: c["position"] for c in b.cursors(W)}
    assert rows["hooks"] == str(len(open(env.spec.hooks, "rb").read()))
    assert rows[SID] == str(env.transcript().stat().st_size)
    assert json.loads(rows["reader"])["hooks"] == int(rows["hooks"])


def test_a_half_written_line_waits_for_the_rest(env):
    env.start()
    line = json.dumps(human("u1", 1, "还没写完", "p1"))
    with open(env.transcript(), "w") as f:
        f.write(line[:20])
    r = ClaudeReader(env.spec)
    step(r)
    assert r.state["files"][SID]["offset"] == 0
    with open(env.transcript(), "a") as f:
        f.write(line[20:] + "\n")
    _, points = flat(step(r))
    assert [p["body"] for p in points if p["event"] == "agent.message"] == ["还没写完"]


def test_unknown_record_types_are_counted_on_the_session(env):
    env.start()
    env.write([{"type": "brand-new-thing", "uuid": "z1", "timestamp": ts(1)}, {"type": "mode", "mode": "normal"}])
    spans, points = flat(step(ClaudeReader(env.spec)))
    assert spans["agent.session"][0]["memorytalk.unrecognized"] == 1              # 认识但不进 trace 的(mode)不算
    assert [p["event"] for p in points] == ["agent.state"]


def test_sidechain_lines_are_skipped(env):
    env.start()
    side = human("s1", 1, "子 agent 的话", "p1")
    side["isSidechain"] = True
    env.write([side])
    spans, points = flat(step(ClaudeReader(env.spec)))
    assert "agent.turn" not in spans and [p["event"] for p in points] == ["agent.state"]


def test_finish_ends_whatever_is_open_with_the_reason(env):
    env.start()
    env.write([human("u1", 1, "x", "p1"), call("a1", 2, "toolu_1", "Bash", {"command": "make"}, "m1")])
    r = ClaudeReader(env.spec)
    step(r)
    spans, _ = flat(step(r, finish=("detached", 1)))
    assert [(s["memorytalk.end.reason"], s["end"]) for s in spans["agent.tool"] + spans["agent.turn"] + spans["agent.session"]] == \
        [("detached", ns(2)), ("detached", ns(2)), ("detached", ns(2))]


def test_a_long_transcript_is_pushed_in_several_batches(env, monkeypatch):
    monkeypatch.setattr(reader_mod, "RECORD_BUDGET", 3)
    env.start()
    env.write([human("u1", 1, "x", "p1")] + [say(f"a{i}", 2 + i, f"第 {i} 段", f"m{i}", stop=None) for i in range(7)])
    r, uids, drained = ClaudeReader(env.spec), [], []
    while True:
        b = step(r)
        uids += [p["log.record.uid"] for p in flat(b)[1] if p["event"] == "agent.message"]
        drained.append(b.drained)
        if b.drained:
            break
    assert uids == [f"{W}:u1"] + [f"{W}:a{i}:0" for i in range(7)] and drained[0] is False
