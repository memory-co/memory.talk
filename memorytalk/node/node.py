"""节点里的一份:盯着哪些工作单元,一轮一轮读、推给中心;中心说 watch / flush / list(work-node.md §7)。

- 每个盯着的工作单元一个上报任务(进程里的一个对象,不是进程、不是线程):一个后台循环轮着看,只 stat,变了才读。
- 推不成功(中心没起来、网络断了)不挪游标,下次从老地方重读:会话记录本身就是缓冲,节点不攒队列。
  中心明确拒收(4xx)的那批记日志丢掉,不卡住后面的。
- 推到哪了存在中心(随每一批一起写进 trace_cursors);节点重启从中心读回来接着读。
  盯着谁存在本地 worklets/<id>/watch.json,节点重启后自己接着盯;中心重启后再说一遍 watch 也没事(幂等)。
- 现场没了(tmux 会话不在了)由这里发现:读到头,开着的段按 gone 结束(status Unset),再给 worklet 段补一个 gone 结束。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Protocol

from . import layout, otlp
from .claude import Batch, ClaudeReader, Spec, restore

log = logging.getLogger(__name__)

STEPS_PER_POLL = 8             # 一轮里一个工作单元最多推几批(大的会话记录分几轮追上,别的工作单元不用等)
READERS = {"claude": ClaudeReader}


class Rejected(Exception):
    """中心不收这一批(4xx):重推也没用。"""


class Center(Protocol):
    """节点眼里的中心:推一批、问推到哪了。"""
    def push(self, work_id: str, body: dict) -> dict: ...
    def cursors(self, work_id: str, worklet_id: str) -> list[dict]: ...


class Watch:
    def __init__(self, spec: Spec) -> None:
        self.spec = spec
        self.reader: ClaudeReader | None = None          # 从中心读回游标之后才有
        self.last_alive = time.time_ns()


class Node:
    def __init__(self, node_dir: Path, center: Center) -> None:
        self.node_dir = Path(node_dir)
        self.center = center
        self.watching: dict[str, Watch] = {}
        self._lock = threading.RLock()

    # ================================================================ 中心说

    def watch(self, spec: dict) -> dict:
        """起一个上报任务(已经在盯就换上新的说明:重入开了新的 worklet 段、现场重开换了会话 id)。"""
        s = Spec.of(spec)
        if s.server not in READERS:
            raise ValueError(f"节点不会读 {s.server!r}")
        with self._lock:
            w = self.watching.get(s.worklet_id)
            if w is None:
                w = self.watching[s.worklet_id] = Watch(s)
            elif w.reader is not None:
                w.reader.rebase(s)
            w.spec = s
            path = layout.watch_file(self.node_dir, s.worklet_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(s.dump(), ensure_ascii=False))
            try:
                self._step(w)                              # 先读一步:接上中心那边已经有的
            except Exception:                              # 推不上去不要紧,后台循环接着推
                log.warning("刚盯上的 %s 第一批没推上去", s.worklet_id, exc_info=True)
        return {"watching": s.worklet_id}

    def flush(self, worklet_id: str, reason: str) -> dict:
        """读到头、推完,开着的段按 reason 结束,不再盯。detached = 工作单元没了,它的目录一起删。"""
        with self._lock:
            w = self.watching.get(worklet_id)
            flushed = False
            if w is not None:
                flushed = self._finish(w, reason, otlp.STATUS_OK)
                if flushed:
                    self._forget(worklet_id)
            if reason == "detached" and (w is None or flushed):
                shutil.rmtree(layout.worklet_dir(self.node_dir, worklet_id), ignore_errors=True)
        return {"flushed": flushed, "watching": w is not None}

    def list(self) -> dict:
        with self._lock:
            return {"watching": sorted(self.watching),
                    "sessions": {k: sorted(v) for k, v in (self._sessions() or {}).items()}}

    # ================================================================ 后台循环:一轮

    def load(self) -> None:
        """节点起来:接着盯上次在盯的(游标第一次推的时候从中心读)。"""
        for path in sorted((self.node_dir / "worklets").glob("*/watch.json")):
            try:
                s = Spec.of(json.loads(path.read_text()))
            except (ValueError, TypeError, KeyError):
                log.warning("watch.json 坏了,不接着盯:%s", path)
                continue
            self.watching.setdefault(s.worklet_id, Watch(s))

    def poll(self) -> None:
        with self._lock:
            sessions = self._sessions()
            for w in list(self.watching.values()):
                try:
                    live = sessions.get(w.spec.tmux_socket) if sessions is not None and w.spec.tmux_socket else None
                    if live is not None and w.spec.worklet_id not in live:
                        if self._finish(w, "gone", otlp.STATUS_UNSET):
                            self._forget(w.spec.worklet_id)
                        continue
                    w.last_alive = time.time_ns()
                    for _ in range(STEPS_PER_POLL):
                        if not self._step(w):
                            break
                except Exception:
                    log.exception("上报出错:%s", w.spec.worklet_id)

    def _step(self, w: Watch, finish: tuple[str, int] | None = None, extra: list[dict] = ()) -> bool:
        """读一步、推一批;交回「还有没读完的」。推不成功就抛出去,游标不动。"""
        if w.reader is None:
            w.reader = READERS[w.spec.server](w.spec, restore(w.spec, self.center.cursors(w.spec.work_id, w.spec.worklet_id)))
        batch = w.reader.step(finish)
        for s in extra:
            batch.spans[s["spanId"]] = s
        if batch.empty() and batch.state == w.reader.state:
            return not batch.drained
        self._push(w, batch)
        w.reader.commit(batch)
        return not batch.drained

    def _push(self, w: Watch, batch: Batch) -> None:
        body = {**batch.document(), "cursors": batch.cursors(w.spec.worklet_id)}
        try:
            self.center.push(w.spec.work_id, body)
        except Rejected as e:                               # 中心不收:记下来、跳过这一批,别卡住后面
            log.error("中心拒收 %s 的一批(%d 段 %d 点):%s", w.spec.worklet_id, len(batch.spans), len(batch.records), e)

    def _finish(self, w: Watch, reason: str, status: int) -> bool:
        """读到头、推完、结束开着的段;现场没了另给 worklet 段补一个 gone 结束。推不上去 = 没 flush 完(交回 False)。"""
        try:
            while self._step(w):
                pass
            extra = []
            if reason == "gone":
                extra = [otlp.span(w.spec.trace_id, w.spec.parent, None, "worklet", w.spec.since or w.last_alive,
                                   {"memorytalk.end.reason": "gone"}, end=w.last_alive, status=otlp.STATUS_UNSET)]
            while self._step(w, (reason, status), extra):
                extra = []
            return True
        except Exception:
            log.exception("没 flush 完:%s(%s)", w.spec.worklet_id, reason)
            return False

    def _forget(self, worklet_id: str) -> None:
        self.watching.pop(worklet_id, None)
        layout.watch_file(self.node_dir, worklet_id).unlink(missing_ok=True)

    def _sessions(self) -> dict[str, set[str]] | None:
        """本机各个 tmux socket 上活着的会话。问不出来(没装 tmux)= None,这时不判现场没了。"""
        sockets = {w.spec.tmux_socket for w in self.watching.values() if w.spec.tmux_socket}
        out: dict[str, set[str]] = {}
        for sock in sockets:
            try:
                r = subprocess.run(["tmux", "-L", sock, "list-sessions", "-F", "#{session_name}"],
                                   capture_output=True, text=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                return None
            if r.returncode == 0:
                out[sock] = set(r.stdout.split())
            elif "no server running" in r.stderr or "error connecting" in r.stderr or "No such file" in r.stderr:
                out[sock] = set()                            # 这个 socket 上的 tmux 都没了
            else:
                return None
        return out


__all__ = ["Node", "Center", "Rejected"]
