"""bash → trace:一条命令是一轮(work-server-io.md §6)。和 claude 一个样子:会话段 → 轮次段,人那句 = 命令,回复 = 它的输出。

边界由 bash 自己报(shell 集成;layout.bash_rc 生成的 rcfile,开现场时用 `bash --rcfile` 起),一行一个事件:
- start   bash 起来了(pid、版本、目录)
- cmd     一条命令开始执行(PS0 里写):命令原文;前面加了空格、没进历史的是 hidden,原文和输出都不记
- done    回到提示符之前(PROMPT_COMMAND 里写):退出码、现在的目录,和一个文件——这条命令开始到结束之间那一段屏幕,
          由 tmux capture-pane 取的渲染好的文字(没有控制字符;进度条只剩最后的样子;全屏程序退出后什么都不留)
节点只读这个事件文件(和输出文件),中心不认识 bash。状态:cmd → busy,done → idle。
退出码 130(Ctrl-C)这一轮记成 cancelled;退出码记在轮次段的 process.exit.code 上。
"""
from __future__ import annotations

import copy
import os

from . import otlp
from .base import Batch, Spec, read_lines, saved_state

READ_BUDGET = 1 << 20          # 一步最多读这么多字节的事件
RECORD_BUDGET = 400            # 一批最多这么多个点
OUTPUT_LIMIT = 64 << 10        # 一条命令的输出最多记这么多字节:前 16 KiB + 后 48 KiB,中间写省略了多少
OUTPUT_HEAD = 16 << 10


def fresh() -> dict:
    return {"hooks": 0, "seg": None, "turn": None, "state": None, "t": 0}


class BashReader:
    def __init__(self, spec: Spec, state: dict | None = None) -> None:
        self.spec = spec
        self.state = state or fresh()

    @classmethod
    def restored(cls, spec: Spec, cursors: list[dict]) -> "BashReader":
        st = fresh()
        st.update(saved_state(cursors) or {})
        return cls(spec, st)

    def step(self, finish: tuple[str, int] | None = None) -> Batch:
        s = _Step(self.spec, copy.deepcopy(self.state))
        s.run()
        if finish and s.batch.drained:
            s.close_all(*finish)
        s.batch.state = s.st
        return s.batch

    def commit(self, batch: Batch) -> None:
        self.state = batch.state
        for path in batch.cleanup:                                 # 输出已经进了 trace:文件删掉
            try:
                os.unlink(path)
            except OSError:
                pass

    def rebase(self, spec: Spec) -> None:
        if spec.parent != self.spec.parent:                        # 重入开了新的 worklet 段:旧段里开着的已经跟着结束了
            self.state.update(seg=None, turn=None, state=None)
        self.spec = spec


class _Step:
    def __init__(self, spec: Spec, st: dict) -> None:
        self.spec, self.st, self.w = spec, st, spec.worklet_id
        self.batch = Batch()

    def run(self) -> None:
        lines, drained = read_lines(self.spec.hooks, self.st["hooks"], READ_BUDGET)
        self.batch.drained = drained
        for start, end, d in lines:
            if len(self.batch.records) >= RECORD_BUDGET:
                self.batch.drained = False
                break
            self.st["hooks"] = end
            if d:
                self._event(d, f"{self.w}:hook:{start}")

    def _event(self, d: dict, uid: str) -> None:
        at = d["ts"] if isinstance(d.get("ts"), int) else self.st["t"]
        self.st["t"] = max(self.st["t"], at)
        kind = d.get("e")
        if kind == "start":
            self._open_seg(uid, at, d)
            self._state("idle", at, uid)
        elif kind == "cmd":
            self._cmd(uid, at, d)
        elif kind == "done":
            self._done(uid, at, d)

    # ================================================================ 事件

    def _cmd(self, uid: str, at: int, d: dict) -> None:
        if self.st["seg"] is None:                                 # 没看到 start(事件文件是后来才有的):这一条开会话段
            self._open_seg(uid, at, {})
        if self.st["turn"]:                                        # 上一条没报 done(shell 被 exec 换掉了之类)
            self._end_turn("cancelled", None)
        seg = self.st["seg"]
        self.st["turn"] = {"id": otlp.turn_span_id(self.w, uid), "uid": uid, "parent": seg["id"], "start": at, "last": at,
                           "cwd": d.get("cwd"), "count": 0}
        hidden = bool(d.get("hidden"))
        self._point(self.st["turn"]["id"], "agent.message", at, uid,
                    {"memorytalk.message.role": "user", "memorytalk.message.kind": "text",
                     "memorytalk.message.hidden": True if hidden else None}, "" if hidden else str(d.get("cmd") or ""))
        self.st["turn"]["count"] += 1
        self._emit_turn()
        self._state("busy", at, uid)

    def _done(self, uid: str, at: int, d: dict) -> None:
        turn = self.st["turn"]
        path = d.get("out") or ""
        if path:
            self.batch.cleanup.append(path)
        if not turn:
            return
        output = _clip(_read(path)) if path else ""
        if output.strip():
            self._point(turn["id"], "agent.message", at, uid, {"memorytalk.message.role": "assistant", "memorytalk.message.kind": "output"},
                        output)
            turn["count"] += 1
        code = d.get("code") if isinstance(d.get("code"), int) else None
        self._end_turn("cancelled" if code == 130 else "completed", at, code=code, cwd=d.get("cwd"))
        self._state("idle", at, uid)

    # ================================================================ 段

    def _open_seg(self, uid: str, at: int, d: dict) -> None:
        if self.st["seg"]:
            self._end_seg("replaced", at)
        pid = d.get("pid")
        self.st["seg"] = {"id": otlp.session_span_id(self.w, f"bash:{pid or '?'}", uid), "parent": self.spec.parent,
                          "start": at, "last": at, "pid": pid, "version": d.get("bash"), "cwd": d.get("cwd")}
        self.st["state"] = None
        self._emit_seg()

    def _end_seg(self, reason: str, at: int | None, status: int = otlp.STATUS_OK) -> None:
        seg = self.st["seg"]
        if self.st["turn"]:
            self._end_turn("cancelled" if reason in ("replaced", "completed") else reason, None, status)
        self._emit_seg(end=max(seg["last"], at or 0), reason=reason, status=status)
        self.st["seg"] = None

    def _end_turn(self, reason: str, at: int | None, status: int = otlp.STATUS_OK, *, code: int | None = None,
                  cwd: str | None = None) -> None:
        turn = self.st["turn"]
        end = max(turn["last"] if at is None else at, turn["start"])
        self._emit_turn(end=end, reason=reason, status=status, code=code, cwd=cwd)
        if self.st["seg"]:
            self.st["seg"]["last"] = max(self.st["seg"]["last"], end)
        self.st["turn"] = None

    def close_all(self, reason: str, status: int) -> None:
        """flush / 现场没了:开着的这一轮(命令还在跑)和会话段按这个原因结束。"""
        if self.st["turn"]:
            self._end_turn(reason, None, status)
        if self.st["seg"]:
            self._end_seg(reason, None, status)

    def _emit_seg(self, end: int | None = None, reason: str | None = None, status: int = otlp.STATUS_UNSET) -> None:
        seg = self.st["seg"]
        attrs = {"memorytalk.worklet.id": self.w, "memorytalk.agent": "bash", "process.pid": seg["pid"],
                 "memorytalk.shell.version": seg["version"], "memorytalk.shell.cwd": seg["cwd"], "memorytalk.end.reason": reason}
        self.batch.spans[seg["id"]] = otlp.span(self.spec.trace_id, seg["id"], seg["parent"], "agent.session", seg["start"], attrs,
                                                end=end, status=status if end is not None else otlp.STATUS_UNSET)

    def _emit_turn(self, end: int | None = None, reason: str | None = None, status: int = otlp.STATUS_UNSET, *,
                   code: int | None = None, cwd: str | None = None) -> None:
        turn = self.st["turn"]
        attrs = {"memorytalk.worklet.id": self.w, "memorytalk.agent": "bash", "memorytalk.shell.cwd": turn["cwd"],
                 "memorytalk.message.count": turn["count"], "process.exit.code": code, "memorytalk.end.reason": reason,
                 "memorytalk.end.shell.cwd": cwd if cwd != turn["cwd"] else None}
        self.batch.spans[turn["id"]] = otlp.span(self.spec.trace_id, turn["id"], turn["parent"], "agent.turn", turn["start"], attrs,
                                                 end=end, status=status if end is not None else otlp.STATUS_UNSET)

    # ================================================================ 点

    def _state(self, value: str, at: int, cause_uid: str) -> None:
        if self.st["state"] == value or not self.st["seg"]:
            return
        self.st["state"] = value
        self._point(self.st["seg"]["id"], "agent.state", at, f"{cause_uid}:state", {"memorytalk.state": value})

    def _point(self, span_id: str, event: str, at: int, uid: str, attrs: dict, body: str | None = None) -> None:
        self.batch.records.append(otlp.record(self.spec.trace_id, span_id, event, at, uid,
                                              {"memorytalk.worklet.id": self.w, **attrs}, body))
        if self.st["turn"]:
            self.st["turn"]["last"] = max(self.st["turn"]["last"], at)
        if self.st["seg"]:
            self.st["seg"]["last"] = max(self.st["seg"]["last"], at)


def _read(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""                                                  # 推过又重读(文件已经删了):就当没有输出


def _clip(text: str) -> str:
    """一条命令的输出:去掉末尾的空行;太长就留头留尾,中间写省略了多少字节。"""
    text = text.rstrip("\n")
    data = text.encode()
    if len(data) <= OUTPUT_LIMIT:
        return text
    head = data[:OUTPUT_HEAD].decode(errors="ignore")
    tail = data[-(OUTPUT_LIMIT - OUTPUT_HEAD):].decode(errors="ignore")
    return f"{head}\n…(中间省略 {len(data) - OUTPUT_LIMIT} 字节)…\n{tail}"


__all__ = ["BashReader", "fresh"]
