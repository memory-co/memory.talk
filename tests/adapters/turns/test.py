"""adapters/turns -- slicing rounds into agent turns, and each adapter's timestamps into Unix nanos. See README.md."""
import json

from memorytalk.backend.models.work import Round
from memorytalk.backend.services.work.turns import round_time_ns, slice_turns
from memorytalk.backend.services.work_servers.adapters import CodexAdapter, KimiAdapter

S = 1_000_000_000
T0 = 1788602400                     # 2026-09-05T10:00:00Z


def R(id, role, ts=None):
    """一条 round;ts 给数字就写成 Kimi 那样的 Unix 秒串。"""
    return Round(id=id, role=role, timestamp=None if ts is None else str(ts), text="x")


# ---- 时刻:各 adapter 的写法 → Unix 纳秒 ----

def test_iso_with_z_or_offset():
    assert round_time_ns("2026-09-05T10:00:00Z") == T0 * S
    assert round_time_ns("2026-09-05T18:00:00+08:00") == T0 * S
    assert round_time_ns("2026-09-05T10:00:00") == T0 * S                         # 没写时区当 UTC


def test_iso_fractions_keep_up_to_nanoseconds():
    assert round_time_ns("2026-09-05T10:00:00.5Z") == T0 * S + 500_000_000
    assert round_time_ns("2026-09-05T10:00:00.123456789Z") == T0 * S + 123_456_789


def test_epoch_seconds_as_number_or_string():
    assert round_time_ns(T0) == round_time_ns(str(T0)) == T0 * S
    assert round_time_ns("1788602400.25") == T0 * S + 250_000_000


def test_unparseable_is_none():
    assert [round_time_ns(v) for v in (None, "", "t1", "nan", True)] == [None] * 5


# ---- 切轮次 ----

def test_a_turn_runs_from_a_human_round_to_the_next():
    turns = slice_turns([R("h1", "human", T0), R("a1", "assistant", T0 + 5), R("t1", "tool", T0 + 6),
                         R("h2", "human", T0 + 60), R("a2", "assistant", T0 + 70)])
    assert [(t.first, t.last, t.count) for t in turns] == [("h1", "t1", 3), ("h2", "a2", 2)]
    assert (turns[0].start, turns[0].end, turns[0].closed) == (T0 * S, (T0 + 6) * S, True)


def test_the_last_turn_stays_open():
    [t] = slice_turns([R("h1", "human", T0), R("a1", "assistant", T0 + 5)])
    assert t.closed is False and t.end is None and t.last_at == (T0 + 5) * S


def test_rounds_before_the_first_human_belong_to_no_turn():
    turns = slice_turns([R("s0", "system", T0 - 9), R("a0", "assistant", T0 - 5), R("h1", "human", T0)])
    assert [(t.first, t.count) for t in turns] == [("h1", 1)]


def test_system_and_tool_rounds_do_not_start_a_turn():
    [t] = slice_turns([R("h1", "human", T0), R("s1", "system", T0 + 1), R("t1", "tool", T0 + 2)])
    assert (t.first, t.last, t.count) == ("h1", "t1", 3)


def test_a_round_without_time_inherits_the_previous_one():
    turns = slice_turns([R("h1", "human", T0), R("a1", "assistant"), R("h2", "human"), R("a2", "assistant", T0 + 9)])
    assert (turns[0].end, turns[1].start) == (T0 * S, T0 * S)


def test_a_turn_without_any_time_is_skipped():
    turns = slice_turns([R("h1", "human"), R("a1", "assistant"), R("h2", "human", T0)])
    assert [t.first for t in turns] == ["h2"]


def test_the_end_never_precedes_the_start():
    [t, _] = slice_turns([R("h1", "human", T0 + 10), R("a1", "assistant", T0), R("h2", "human", T0 + 20)])
    assert t.end == t.start == (T0 + 10) * S


def test_no_rounds_no_turns():
    assert slice_turns([]) == []


# ---- 真实的 adapter 输出 ----

def test_kimi_epoch_seconds(home):
    sd = home / "kimi" / "wd_u" / "session_1"; (sd / "agents" / "main").mkdir(parents=True)
    (sd / "state.json").write_text(json.dumps({"workDir": "/w/p"}))
    wire = sd / "agents" / "main" / "wire.jsonl"
    rows = [{"type": "turn.prompt", "time": T0 + 0.5, "input": [{"type": "text", "text": "拉个镜像"}]},
            {"type": "context.append_loop_event", "time": T0 + 3, "event": {"type": "content.part", "uuid": "c1", "part": {"type": "text", "text": "好"}}},
            {"type": "turn.prompt", "time": T0 + 9, "input": [{"type": "text", "text": "再来"}]}]
    wire.write_text("".join(json.dumps(r) + "\n" for r in rows))
    first, second = slice_turns(KimiAdapter(home / "kimi").rounds(wire))
    assert (first.start, first.end, first.count) == (T0 * S + 500_000_000, (T0 + 3) * S, 2)
    assert (second.start, second.end) == ((T0 + 9) * S, None)


def test_codex_iso_timestamps(home):
    root = home / "codex" / "2026" / "09" / "05"; root.mkdir(parents=True)
    p = root / "rollout-x.jsonl"
    rows = [{"type": "session_meta", "payload": {"cwd": "/w/p"}},
            {"type": "event_msg", "timestamp": "2026-09-05T10:00:00.250Z", "payload": {"type": "user_message", "message": "hi"}},
            {"type": "event_msg", "timestamp": "2026-09-05T10:00:04.000Z", "payload": {"type": "agent_message", "message": "done"}}]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    [t] = slice_turns(CodexAdapter(home / "codex").rounds(p))
    assert (t.start, t.last_at, t.count, t.closed) == (T0 * S + 250_000_000, (T0 + 4) * S, 2, False)
