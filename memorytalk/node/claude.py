"""Claude Code → trace(work-trace.md §2、§5):读它的会话记录和 hooks 事件文件,切成会话 / 轮次 / 工具段,
每条消息一个点,状态变了打一个点。中心不认识这些格式,知识都在这里。

两份来源,按时刻合着读:
- 会话记录 `<projects>/*/<会话 id>.jsonl`:开现场时 `--session-id` 钉住了会话 id,按文件名找(或者 hook 直接报路径)。
  一行一条:`user`(人的输入、工具结果、注入的提示、本地命令、打断)、`assistant`(一行一块:文字 / 思考 / 工具调用)、
  `system`(`turn_duration` = 一轮收完)……其余几十种(attachment、mode、ai-title……)不进 trace,不认识的计数。
- hooks 事件(`--settings` 注入,hook.py 一行一个):`SessionStart`(新会话:启动、/clear、/resume,带会话 id 和记录路径)、
  `SessionEnd`、`UserPromptSubmit` / `Stop`(一轮的起止,带 prompt_id)、`Notification`(在等人确认)、`PreToolUse` / `PostToolUse`。

怎么切:
- 会话段:SessionStart 开(没有 hooks 就在看到这份记录的第一条时开);下一个会话开了就结束(replaced),SessionEnd 也结束它。
- 轮次段:人的一条输入开(id 由这条输入的 uid 算);Stop hook 结束(completed;有 prompt_id 就对上是哪一轮),
  没有 hooks 时看 `turn_duration` 或 `stop_reason = end_turn` 且没有没回来的工具调用;「[Request interrupted…」= 打断(cancelled);
  人又说了一句而上一轮还开着,上一轮按 completed 收。
- 工具段:tool_use 开、对应的 tool_result 结束(is_error → status Error);轮次先结束了就跟着结束(cancelled)。
- 状态点:busy(人发了一句 / 批准后接着跑)、idle(一轮收完、被打断、会话刚开)、blocked(Notification:等人批准)。
- 子 agent 现在写在单独的文件里,主记录里的 isSidechain 行跳过;子 agent 怎么挂(work-trace.md §2)以后再接。

一步(step)= 把两份来源从上次读到的地方读到现在,交回一批(段、点、读完以后的状态);推成功了才 commit,
推不成功下次从老地方重读——同样的字节算出同样的 id 和 uid,中心按它们去重,所以「至少一次」就够了。
"""
from __future__ import annotations

import copy
import glob
import heapq
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import otlp

SYSTEM = "anthropic"
READ_BUDGET = 4 << 20          # 一步最多读这么多字节(大的会话记录分几步推完)
RECORD_BUDGET = 400            # 一批最多这么多个点
FIND_EVERY = 2.0               # 秒;会话记录还没出现时多久按文件名找一次(有 SessionStart hook 报路径就不用找)
KNOWN = {"user", "assistant", "system", "attachment", "file-history-snapshot", "file-history-delta", "queue-operation",
         "last-prompt", "mode", "permission-mode", "atis-latch", "ai-title", "custom-title", "agent-name",
         "bridge-session", "cost-state", "summary", "progress", "tag", "pr-link"}
LOCAL = ("<command-name>", "<command-message>", "<local-command-")


@dataclass
class Spec:
    """中心让节点盯一个工作单元时给的说明(watch)。"""
    work_id: str
    worklet_id: str
    trace_id: str
    parent: str                         # 这个工作单元现在开着的那段 worklet 段:会话段挂在它下面
    hooks: str                          # hooks 事件文件
    transcripts: str                    # 会话记录根(~/.claude/projects)
    session_id: str | None = None       # 开现场时钉住的会话 id
    server: str = "claude"
    cwd: str | None = None
    tmux_socket: str | None = None      # 看现场活没活着:tmux -L <它>
    since: int = 0                      # 工作单元打开的时刻(Unix 纳秒)

    @classmethod
    def of(cls, d: dict) -> "Spec":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def dump(self) -> dict:
        return asdict(self)


def fresh(spec: Spec) -> dict:
    """还什么都没读过的状态。整个状态是 JSON:随推的那一批存进中心(cursors),重启从中心读回来。"""
    return {"hooks": 0, "files": {}, "current": spec.session_id, "seg": None, "prev": {}, "turn": None, "tools": {},
            "state": None, "hooked": False, "unrecognized": 0, "t": 0}


def restore(spec: Spec, cursors: list[dict]) -> dict:
    st = fresh(spec)
    for c in cursors:
        if c["source"] == "reader":
            st.update(json.loads(c["position"]))
    return st


@dataclass
class Batch:
    spans: dict[str, dict] = field(default_factory=dict)       # span id → 这一步结束时它的样子(开着的合并属性,结束的定稿)
    records: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    drained: bool = True                                       # 两份来源都读到头了

    def empty(self) -> bool:
        return not self.spans and not self.records

    def cursors(self, worklet_id: str) -> list[dict]:
        """推到哪了:hooks 和每份会话记录各一行(给人看的),reader 一行是整个状态(重启用它)。"""
        st = self.state
        rows = [{"worklet_id": worklet_id, "source": "hooks", "position": str(st["hooks"])}]
        rows += [{"worklet_id": worklet_id, "source": sid, "position": str(f["offset"])} for sid, f in st["files"].items()]
        rows.append({"worklet_id": worklet_id, "source": "reader", "position": json.dumps(st, ensure_ascii=False)})
        return rows

    def document(self) -> dict:
        return otlp.document(list(self.spans.values()), self.records)


class ClaudeReader:
    def __init__(self, spec: Spec, state: dict | None = None) -> None:
        self.spec = spec
        self.state = state or fresh(spec)
        self._looked: dict[str, float] = {}                    # 会话记录还没出现:多久找一次(不进状态)

    def step(self, finish: tuple[str, int] | None = None) -> Batch:
        """读一步。finish = (原因, status):读到头了就把开着的工具 / 轮次 / 会话段按这个原因结束(flush、现场没了)。
        不改 self.state;推成功了再 commit。"""
        s = _Step(self.spec, copy.deepcopy(self.state), self._find)
        s.run()
        if finish and s.batch.drained:
            s.close_all(*finish)
        s.batch.state = s.st
        return s.batch

    def commit(self, batch: Batch) -> None:
        self.state = batch.state

    def rebase(self, spec: Spec) -> None:
        """中心又说了一次 watch:worklet 段换了(重入开了新的一段)就从新的一段接着挂——旧段里开着的
        会话 / 轮次 / 工具段已经跟着旧 worklet 段结束了(中心兜底结束,或者现场没了时这里结束的),不再往上写。"""
        if spec.parent != self.spec.parent:
            self.state.update(seg=None, turn=None, tools={}, state=None)
        if spec.session_id and spec.session_id != self.spec.session_id:
            self.state["current"] = spec.session_id            # 现场重开了,新的 claude 钉的是新的会话 id
        self.spec = spec

    def _find(self, sid: str) -> str | None:
        """按文件名找会话记录;还没有就过一会儿再找(claude 收到第一句话才建这个文件)。"""
        now = time.monotonic()
        if sid in self._looked and now - self._looked[sid] < FIND_EVERY:
            return None
        self._looked[sid] = now
        hits = glob.glob(os.path.join(glob.escape(self.spec.transcripts), "*", f"{glob.escape(sid)}.jsonl"))
        return hits[0] if hits else None


class _Item:
    __slots__ = ("time", "kind", "data", "end", "sid", "uid")

    def __init__(self, time_: int, kind: str, data: dict, end: int, sid: str | None, uid: str) -> None:
        self.time, self.kind, self.data, self.end, self.sid, self.uid = time_, kind, data, end, sid, uid


class _Step:
    def __init__(self, spec: Spec, st: dict, find) -> None:
        self.spec, self.st, self.find = spec, st, find
        self.w = spec.worklet_id
        self.batch = Batch()

    # ================================================================ 读

    def run(self) -> None:
        hooks = self._hooks()
        for it in hooks:                                       # SessionStart 报了记录在哪,先记下
            if it.data.get("hook_event_name") == "SessionStart" and it.data.get("session_id"):
                f = self.st["files"].setdefault(it.data["session_id"], {"path": None, "offset": 0})
                f["path"] = it.data.get("transcript_path") or f["path"]
        sids = [self.st["current"]] if self.st["current"] else []
        sids += [it.data["session_id"] for it in hooks
                 if it.data.get("hook_event_name") == "SessionStart" and it.data.get("session_id") not in sids]
        streams = [hooks] + [self._transcript(sid) for sid in dict.fromkeys(sids)]
        for it in heapq.merge(*streams, key=lambda it: it.time):
            if len(self.batch.records) >= RECORD_BUDGET:
                self.batch.drained = False
                break
            if it.kind == "hook":
                self.st["hooks"] = it.end
                if it.data:
                    self.st["hooked"] = True
                    self._hook(it)
            else:
                self.st["files"][it.sid]["offset"] = it.end
                if it.data:
                    self._record(it)

    def _hooks(self) -> list[_Item]:
        out = []
        last = self.st["t"]
        for start, end, d in self._lines(self.spec.hooks, self.st["hooks"]):
            if d is None:                                      # 坏行:跳过,但游标照样按顺序往前挪
                out.append(_Item(last, "hook", {}, end, None, ""))
                continue
            last = d.get("_ts") if isinstance(d.get("_ts"), int) else last
            out.append(_Item(last, "hook", d, end, d.get("session_id"), f"{self.w}:hook:{start}"))
        return out

    def _transcript(self, sid: str) -> list[_Item]:
        f = self.st["files"].setdefault(sid, {"path": None, "offset": 0})
        if not f["path"] or not os.path.exists(f["path"]):
            f["path"] = self.find(sid) or f["path"]
            if not f["path"]:
                return []
        out = []
        last = self.st["t"]
        for start, end, d in self._lines(f["path"], f["offset"]):
            if d is None:
                out.append(_Item(last, "record", {}, end, sid, ""))
                continue
            last = _nanos(d.get("timestamp")) or last
            uid = f"{self.w}:{d['uuid']}" if d.get("uuid") else f"{self.w}:{sid}:{start}"
            out.append(_Item(last, "record", d, end, sid, uid))
        return out

    def _lines(self, path: str, offset: int):
        """从 offset 读到现在为止完整的行(最后半行不要,下次再读);一次最多 READ_BUDGET 字节,但至少一整行。"""
        try:
            with open(path, "rb") as fh:
                size = os.fstat(fh.fileno()).st_size
                if size <= offset:
                    return []
                fh.seek(offset)
                data = fh.read(min(size - offset, READ_BUDGET))
                if b"\n" not in data and offset + len(data) < size:
                    data += fh.readline()                      # 一行比预算还大:整行读完
        except FileNotFoundError:
            return []
        if offset + len(data) < size:                          # 预算到了,后面还有:这一步没读到头
            self.batch.drained = False
        out, pos = [], 0
        while (nl := data.find(b"\n", pos)) >= 0:
            raw = data[pos:nl]
            try:
                d = json.loads(raw) if raw.strip() else None
            except ValueError:
                d = None
            out.append((offset + pos, offset + nl + 1, d if isinstance(d, dict) else None))
            pos = nl + 1
        return out

    # ================================================================ hooks

    def _hook(self, it: _Item) -> None:
        d, at = it.data, it.time
        event = d.get("hook_event_name")
        self.st["t"] = max(self.st["t"], at)                            # hook 不算轮次 / 会话里的动静(终点只看记录)
        if event == "SessionStart":
            sid, source = d.get("session_id"), d.get("source")
            seg = self.st["seg"]
            if seg and seg["sid"] == sid and source == "compact":        # /compact:同一个会话接着写
                return
            if seg and seg["sid"] == sid and seg["source"] is None:      # 这个会话的记录比 hook 先到(/clear 就是):段已经开了,补上来源
                seg["source"] = source
                self._emit_seg()
            else:
                self._open_seg(sid, it.uid, at, source)
            self._state("idle", at, it.uid)
        elif event == "SessionEnd":
            seg = self.st["seg"]
            if seg and seg["sid"] == d.get("session_id"):
                self._end_seg("replaced" if d.get("reason") == "clear" else "completed", at)
        elif event == "UserPromptSubmit":
            self._state("busy", at, it.uid)
        elif event == "Stop":
            turn = self.st["turn"]
            if turn and (not d.get("prompt_id") or not turn["prompt"] or d["prompt_id"] == turn["prompt"]):
                self._end_turn("completed", max(turn["last"], at))
            self._state("idle", at, it.uid)
        elif event == "Notification":
            kind, message = d.get("notification_type") or "", (d.get("message") or "").lower()
            if kind == "permission_prompt" or "permission" in message:
                self._state("blocked", at, it.uid)
            elif kind == "idle_prompt" and not self.st["turn"]:
                self._state("idle", at, it.uid)
        elif event in ("PreToolUse", "PostToolUse"):
            if self.st["state"] == "blocked":                           # 批准了,接着跑
                self._state("busy", at, it.uid)

    # ================================================================ 会话记录

    def _record(self, it: _Item) -> None:
        d, at = it.data, it.time
        kind = d.get("type")
        if kind not in KNOWN:
            self.st["unrecognized"] += 1
            if self.st["seg"]:
                self._emit_seg()
            return
        if d.get("isSidechain") or kind not in ("user", "assistant", "system"):
            return
        seg = self.st["seg"]
        if seg is None or seg["sid"] != it.sid:                         # 没有 hook 报这个会话:看到它的第一条就开
            self._open_seg(it.sid, it.uid, at, None)
        msg = d.get("message") or {}
        if kind == "user":
            self._user(it, msg.get("content"), at)
        elif kind == "assistant":
            self._assistant(it, msg, at)
        elif d.get("subtype") == "turn_duration":                       # 一轮收完(没有 Stop hook 时靠它)
            if self.st["turn"]:
                self._end_turn("completed", at)
            self._state("idle", at, it.uid)
        elif d.get("subtype") == "local_command":
            self._message(it.uid, "system", "text", _text(d.get("content")), at)
            if not self.st["turn"]:
                self._state("idle", at, it.uid)
        self._touch(at)                                                 # 处理完再挪「最后一次动静」:人又说一句时,上一轮按它自己最后一条收

    def _user(self, it: _Item, content, at: int) -> None:
        blocks = content if isinstance(content, list) else None
        if blocks and any(b.get("type") == "tool_result" for b in blocks if isinstance(b, dict)):
            for i, b in enumerate(blocks):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    self._tool_result(f"{it.uid}:{i}", b, at)
            return
        text = _text(content)
        if text.startswith("[Request interrupted"):                     # Esc:这一轮被打断
            self._message(it.uid, "system", "text", text, at)
            if self.st["turn"]:
                self._end_turn("cancelled", at)
            self._state("idle", at, it.uid)
            return
        if it.data.get("isMeta") or text.lstrip().startswith(LOCAL):    # 注入的提示、本地命令和它的输出:不算人说的
            self._message(it.uid, "system", "text", text, at)
            if text.lstrip().startswith("<local-command-stdout>") and not self.st["turn"]:
                self._state("idle", at, it.uid)
            return
        turn = self.st["turn"]                                          # 一条输入:开新的一轮
        if turn:
            self._end_turn("completed", turn["last"])
        origin = (it.data.get("origin") or {}).get("kind") or it.data.get("turnOrigin")
        role = "system" if it.data.get("promptSource") == "system" or origin not in (None, "human") else "user"
        self.st["turn"] = {"id": otlp.turn_span_id(self.w, it.uid), "uid": it.uid, "prompt": it.data.get("promptId"),
                           "sid": self.st["seg"]["sid"], "parent": self.st["seg"]["id"], "start": at, "last": at,
                           "count": 0, "usage": {}, "origin": origin}                 # 不是人发的(后台任务回来了之类)也是一轮
        if blocks is None:
            self._message(it.uid, role, "text", text, at)
        else:
            for i, b in enumerate(blocks):
                if isinstance(b, dict) and b.get("type") in ("text", "image"):
                    self._message(f"{it.uid}:{i}", role, "text", b.get("text", "") if b["type"] == "text" else "[image]", at)
        self._emit_turn()
        self._state("busy", at, it.uid)

    def _assistant(self, it: _Item, msg: dict, at: int) -> None:
        turn = self.st["turn"]
        for i, b in enumerate(msg.get("content") or []):
            if not isinstance(b, dict):
                continue
            uid = f"{it.uid}:{i}"
            if b.get("type") == "text" and b.get("text"):
                self._message(uid, "assistant", "text", b["text"], at)
            elif b.get("type") == "thinking" and b.get("thinking"):
                self._message(uid, "assistant", "thinking", b["thinking"], at)
            elif b.get("type") == "tool_use" and b.get("id"):
                self._tool_use(uid, b, at)
        if turn and (usage := msg.get("usage")) and msg.get("id"):
            turn["usage"][msg["id"]] = [int(usage.get(k) or 0) for k in
                                        ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
            self._emit_turn()
        if (turn and msg.get("stop_reason") == "end_turn" and not self.st["hooked"]
                and not any(t["parent"] == turn["id"] for t in self.st["tools"].values())):
            self._end_turn("completed", at)
            self._state("idle", at, it.uid)

    def _tool_use(self, uid: str, b: dict, at: int) -> None:
        turn, seg = self.st["turn"], self.st["seg"]
        call = b["id"]
        tool = {"id": otlp.tool_span_id(self.w, call), "name": b.get("name") or "", "start": at,
                "parent": turn["id"] if turn else seg["id"]}
        self.st["tools"][call] = tool
        self._emit_tool(call)
        self._point(tool["id"], "agent.tool.input", at, uid,
                    {"gen_ai.tool.name": tool["name"], "gen_ai.tool.call.id": call},
                    json.dumps(b.get("input"), ensure_ascii=False))

    def _tool_result(self, uid: str, b: dict, at: int) -> None:
        call = b.get("tool_use_id") or ""
        tool = self.st["tools"].get(call)
        error = bool(b.get("is_error"))
        target = tool["id"] if tool else self._target()
        self._point(target, "agent.tool.output", at, uid, {"gen_ai.tool.call.id": call, "memorytalk.tool.error": error or None},
                    _text(b.get("content")))
        if tool:
            self._end_tool(call, "completed", at, otlp.STATUS_ERROR if error else otlp.STATUS_OK)

    # ================================================================ 段:开、结束、交出去

    def _open_seg(self, sid: str, first_uid: str, at: int, source: str | None) -> None:
        if self.st["seg"]:
            self._end_seg("replaced", at)
        prev = self.st["prev"].get(sid)
        self.st["seg"] = {"id": otlp.session_span_id(self.w, sid, first_uid), "sid": sid, "parent": self.spec.parent,
                          "start": at, "last": at, "source": source, "links": [prev] if prev else []}
        self.st["prev"][sid] = self.st["seg"]["id"]
        self.st["current"] = sid
        self.st["state"] = None                                         # 新会话:状态从头算
        self._emit_seg()

    def _end_seg(self, reason: str, at: int | None = None, status: int = otlp.STATUS_OK) -> None:
        seg = self.st["seg"]
        if self.st["turn"]:
            self._end_turn("cancelled" if reason in ("replaced", "completed") else reason, None, status)
        at = max(seg["last"], at or 0)
        self._emit_seg(end=at, reason=reason, status=status)
        self.st["seg"] = None

    def _end_turn(self, reason: str, at: int | None, status: int = otlp.STATUS_OK) -> None:
        turn = self.st["turn"]
        at = turn["last"] if at is None else at
        for call in [c for c, t in self.st["tools"].items() if t["parent"] == turn["id"]]:
            self._end_tool(call, "cancelled" if reason == "completed" else reason, at, status)
        self._emit_turn(end=max(at, turn["start"]), reason=reason, status=status)
        self.st["turn"] = None

    def _end_tool(self, call: str, reason: str, at: int, status: int) -> None:
        tool = self.st["tools"].pop(call)
        self.batch.spans[tool["id"]] = otlp.span(self.spec.trace_id, tool["id"], tool["parent"], "agent.tool", tool["start"],
                                                 self._tool_attrs(call, tool, reason), end=max(at, tool["start"]), status=status)

    def close_all(self, reason: str, status: int) -> None:
        """flush / 现场没了:开着的工具、轮次、会话段都按这个原因结束,终点取各自最后一次动静。"""
        for call, tool in list(self.st["tools"].items()):
            if not self.st["turn"] or tool["parent"] != self.st["turn"]["id"]:
                self._end_tool(call, reason, tool["start"], status)
        if self.st["turn"]:
            self._end_turn(reason, None, status)
        if self.st["seg"]:
            self._end_seg(reason, None, status)

    def _emit_seg(self, end: int | None = None, reason: str | None = None, status: int = otlp.STATUS_UNSET) -> None:
        seg = self.st["seg"]
        attrs = {"memorytalk.worklet.id": self.w, "gen_ai.conversation.id": seg["sid"], "gen_ai.system": SYSTEM,
                 "memorytalk.session.source": seg["source"], "memorytalk.unrecognized": self.st["unrecognized"],
                 "memorytalk.end.reason": reason}
        self.batch.spans[seg["id"]] = otlp.span(self.spec.trace_id, seg["id"], seg["parent"], "agent.session", seg["start"], attrs,
                                                end=end, status=status if end is not None else otlp.STATUS_UNSET, links=seg["links"])

    def _emit_turn(self, end: int | None = None, reason: str | None = None, status: int = otlp.STATUS_UNSET) -> None:
        turn = self.st["turn"]
        usage = turn["usage"].values()
        tokens = [sum(u[i] for u in usage) for i in range(4)] if usage else None
        attrs = {"memorytalk.worklet.id": self.w, "gen_ai.operation.name": "invoke_agent", "gen_ai.system": SYSTEM,
                 "gen_ai.conversation.id": turn["sid"], "memorytalk.message.count": turn["count"],
                 "memorytalk.turn.origin": turn.get("origin"),
                 "gen_ai.usage.input_tokens": tokens[0] + tokens[2] + tokens[3] if tokens else None,
                 "gen_ai.usage.output_tokens": tokens[1] if tokens else None,
                 "gen_ai.usage.cache_creation.input_tokens": tokens[2] if tokens else None,
                 "gen_ai.usage.cache_read.input_tokens": tokens[3] if tokens else None,
                 "memorytalk.end.reason": reason}
        self.batch.spans[turn["id"]] = otlp.span(self.spec.trace_id, turn["id"], turn["parent"], "agent.turn", turn["start"], attrs,
                                                 end=end, status=status if end is not None else otlp.STATUS_UNSET)

    def _emit_tool(self, call: str) -> None:
        tool = self.st["tools"][call]
        self.batch.spans[tool["id"]] = otlp.span(self.spec.trace_id, tool["id"], tool["parent"], "agent.tool", tool["start"],
                                                 self._tool_attrs(call, tool, None))

    def _tool_attrs(self, call: str, tool: dict, reason: str | None) -> dict:
        return {"memorytalk.worklet.id": self.w, "gen_ai.operation.name": "execute_tool", "gen_ai.system": SYSTEM,
                "gen_ai.tool.name": tool["name"], "gen_ai.tool.call.id": call, "memorytalk.end.reason": reason}

    # ================================================================ 点

    def _target(self) -> str:
        """消息挂哪:这一轮;还没有轮次(第一句人的输入之前、本地命令)就挂会话段。"""
        return self.st["turn"]["id"] if self.st["turn"] else self.st["seg"]["id"]

    def _message(self, uid: str, role: str, kind: str, text: str, at: int) -> None:
        self._point(self._target(), "agent.message", at, uid, {"memorytalk.message.role": role, "memorytalk.message.kind": kind}, text)
        if self.st["turn"]:
            self.st["turn"]["count"] += 1
            self._emit_turn()

    def _state(self, value: str, at: int, cause_uid: str) -> None:
        if self.st["state"] == value or not self.st["seg"]:
            return
        self.st["state"] = value
        self._point(self.st["seg"]["id"], "agent.state", at, f"{cause_uid}:state", {"memorytalk.state": value})

    def _point(self, span_id: str, event: str, at: int, uid: str, attrs: dict, body: str | None = None) -> None:
        self.batch.records.append(otlp.record(self.spec.trace_id, span_id, event, at, uid,
                                              {"memorytalk.worklet.id": self.w, **attrs}, body))

    def _touch(self, at: int) -> None:
        self.st["t"] = max(self.st["t"], at)
        for k in ("seg", "turn"):
            if self.st[k]:
                self.st[k]["last"] = max(self.st[k]["last"], at)


def _nanos(ts) -> int | None:
    """会话记录里的时刻是 ISO 串(Z 结尾,毫秒)→ Unix 纳秒;解不出来 = None(沿用前一条的)。"""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(dt.timestamp()) * 1_000_000_000 + dt.microsecond * 1_000


def _text(content) -> str:
    """消息内容扁平成文字:字符串原样;块列表里的文字接起来,图片写成 [image]。"""
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict):
            if b.get("type") == "text":
                parts.append(b.get("text") or "")
            elif b.get("type") == "image":
                parts.append("[image]")
            elif b.get("type") == "tool_reference":
                parts.append(f"[{b.get('tool_name', 'tool')}]")
        elif isinstance(b, str):
            parts.append(b)
    return "\n".join(parts)


__all__ = ["ClaudeReader", "Spec", "Batch", "fresh", "restore"]
