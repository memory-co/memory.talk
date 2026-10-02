"""轨迹:有起止的记成段(span),一个时刻的事记成点(log record)。字段和 OTel 一对一,落在 worktrace.db(docs/designs/v5/work-trace.md)。

一条写路径,四个动作:start(插一行段,终点为空)、merge(开着的段合并属性)、end(同一行补上终点)、point(追加一行点)。
每个真写了的都在同一个事务里取下一个变更序号(seq),读的游标就是它;写完叫醒等着变化的读(Changes)。
两个写的人进的都是这四个动作:中心自己的动作(人建 work、开工作单元、挪列……)直接调;节点推上来的 OTLP/JSON
(POST /works/{id}/trace)由 ingest 先整批验、再落成这几个动作(work-node.md §6)。
id 由身份算出来:一棵 work 树是一条 trace(trace id 由根 work 算),work / worklet 段的 id 由「谁 + 第几段」算,中心算;
agent 那几层(会话 / 轮次 / 工具段)的 id 节点算,中心按 id 幂等收。
旧的拉取路径(turns:从同步进来的 round 切 agent.turn)只剩 Codex / Kimi 在用,它们改成推以后删掉。
对外(GET /works/{id}/trace)拼成 OTLP/JSON 的 TracesData + LogsData。
写入顺序是先 works.db、后这里;这里写失败不回滚 work,由 WorkService 兜住只记日志。
「查一下再写」的几处(第几段、还开着没有、点有没有)包在 worktrace.db 的事务里;要读 works.db 的(trace id 要走到根)在事务外先算好,
两把锁只会按「worktrace → works」或单独一把的顺序拿。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from typing import Callable, Sequence

from memorytalk.backend.models.work import Column, Round, Work, Worklet

from .repo import TraceRepo
from .tree import WorkTree
from .turns import slice_turns

KIND_INTERNAL = 1
STATUS_UNSET, STATUS_OK, STATUS_ERROR = 0, 1, 2
SCOPE = {"name": "memorytalk.work", "version": "5"}
GEN_AI_SYSTEM = {"claude": "anthropic", "codex": "openai", "kimi": "moonshot"}     # server → OTel GenAI 的 gen_ai.system
AGENT_SPANS, AGENT_POINTS = TraceRepo.AGENT_SPANS, TraceRepo.AGENT_POINTS

log = logging.getLogger(__name__)


def _sha(text: str, n: int) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def trace_id_of(root_work_id: str) -> str:
    """trace id = sha256("memorytalk/trace/" + 根 work id) 的前 16 字节。"""
    return _sha("memorytalk/trace/" + root_work_id, 32)


def work_span_id(work_id: str, segment: int) -> str:
    """work 段的 id = sha256("memorytalk/span/work/<work id>/<第几段>") 的前 8 字节;重新打开一次多一段。"""
    return _sha(f"memorytalk/span/work/{work_id}/{segment}", 16)


def worklet_span_id(worklet_id: str, segment: int) -> str:
    return _sha(f"memorytalk/span/worklet/{worklet_id}/{segment}", 16)


def turn_span_id(worklet_id: str, first_round_id: str) -> str:
    """agent 轮次的 id 由这一轮人那条输入算(节点推的用它的 uid,旧的拉取路径用 round id):同一轮再写一次还是同一个 id。"""
    return _sha(f"memorytalk/span/turn/{worklet_id}/{first_round_id}", 16)


def value(v) -> dict:
    """Python 值 → OTLP AnyValue;64 位整数写成十进制字符串。"""
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def kvs(attrs: dict) -> list[dict]:
    """{key: 值} → OTLP KeyValue 列表;值为 None 的不写。"""
    return [{"key": k, "value": value(v)} for k, v in attrs.items() if v is not None]


def _kvs(attrs: dict | list | None) -> list[dict]:
    """中心自己的动作给 dict,推上来的已经是 KeyValue 列表。"""
    if not attrs:
        return []
    return list(attrs) if isinstance(attrs, list) else kvs(attrs)


def _merge(old: list[dict], new: list[dict]) -> list[dict]:
    keys = {kv["key"] for kv in new}
    return [kv for kv in old if kv["key"] not in keys] + new


def _col(prefix: str, col: Column | None) -> dict:
    """列标记:编号是身份,别名是当时的快照(work-events.md §3)。"""
    if col is None:
        return {}
    return {f"{prefix}column.id": col.id, f"{prefix}column.alias": col.alias}


def _number(col: Column | None) -> int | None:
    return int(col.id[1:]) if col is not None else None


def attr(attrs: list[dict] | None, key: str):
    """OTLP KeyValue 列表里取一个值(AnyValue 解成 Python 值;intValue 解回 int)。"""
    for kv in attrs or []:
        if kv.get("key") == key:
            v = kv.get("value") or {}
            if "intValue" in v:
                return int(v["intValue"])
            for k in ("stringValue", "boolValue", "doubleValue"):
                if k in v:
                    return v[k]
    return None


# ================================================================ 等变化:写在线程里,等在事件循环里

class Changes:
    """trace 有新写入就叫醒等着的读(GET …/trace 的 after + wait,长轮询)。写的一方在工作线程里,
    等的一方在事件循环里,所以跨线程叫醒。先拿票、再查、再等,查和等之间来的变化不会漏。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._waiters: set[Ticket] = set()

    def ticket(self) -> "Ticket":
        t = Ticket(self)
        with self._lock:
            self._waiters.add(t)
        return t

    def notify(self) -> None:
        with self._lock:
            waiters = list(self._waiters)
        for t in waiters:
            t.wake()

    def _drop(self, t: "Ticket") -> None:
        with self._lock:
            self._waiters.discard(t)


class Ticket:
    def __init__(self, changes: Changes) -> None:
        self.changes = changes
        self.loop = asyncio.get_running_loop()
        self.event = asyncio.Event()

    def wake(self) -> None:
        try:
            self.loop.call_soon_threadsafe(self.event.set)
        except RuntimeError:                       # 事件循环已经关了
            pass

    async def wait(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self.event.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            self.close()

    def close(self) -> None:
        self.changes._drop(self)


class TraceRejected(Exception):
    """推上来的一批不收,整批不写:403 = 越界(写了不归节点写的东西),422 = 不成形。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


_HEX = re.compile(r"[0-9a-f]+")


class Trace:
    def __init__(self, repo: TraceRepo, tree: WorkTree, clock: Callable[[], int] = time.time_ns) -> None:
        self.repo = repo
        self.tree = tree
        self.clock = clock
        self.changes = Changes()
        self.resource = {"attributes": kvs({"service.name": "memory.talk"})}

    # ================================================================ 四个动作(每个真写了的取下一个变更序号)

    def start(self, work_id: str, name: str, span_id: str, parent_span_id: str | None, attributes: dict | list, *,
              user: str | None = None, worklet_id: str | None = None, links: Sequence = (),
              at: int | None = None, first_round_id: str | None = None, trace_id: str | None = None,
              kind: int = KIND_INTERNAL) -> bool:
        """插一行段:终点为空,status Unset。同一个 span id 已经有了就跳过;交回这次插没插。"""
        trace_id = trace_id or self.trace_id(work_id)
        with self.repo.tx():
            if self.repo.get_span(span_id) is not None:
                return False
            self.repo.insert_span({
                "span_id": span_id, "trace_id": trace_id, "parent_span_id": parent_span_id,
                "work_id": work_id, "worklet_id": worklet_id, "user_id": user, "end_user_id": None,
                "name": name, "kind": kind,
                "start_time_unix_nano": self.clock() if at is None else at, "end_time_unix_nano": None,
                "status_code": STATUS_UNSET, "attributes": _kvs(attributes) + kvs({"user.id": user}),
                "links": [{"traceId": trace_id, "spanId": s, "attributes": []} if isinstance(s, str) else s for s in links],
                "first_round_id": first_round_id, "seq": self.repo.next_seq()})
        self.changes.notify()
        return True

    def merge(self, span_id: str, attributes: dict | list) -> bool:
        """开着的段合并属性,同名的以新的为准;结束了的不动,没变的不算写。交回这次改没改。"""
        with self.repo.tx():
            row = self.repo.get_span(span_id)
            if row is None or row["end_time_unix_nano"] is not None:
                return False
            merged = _merge(row["attributes"] or [], _kvs(attributes))
            if merged == (row["attributes"] or []):
                return False
            self.repo.update_span(span_id, attributes=merged, seq=self.repo.next_seq())
        self.changes.notify()
        return True

    def end(self, span_id: str, attributes: dict | list | None = None, *, status: int = STATUS_OK,
            user: str | None = None, at: int | None = None) -> bool:
        """在同一行补上终点和结束时的属性;已经结束的不再动(结束即定稿)。交回这次有没有结束它。"""
        with self.repo.tx():                            # 两处同时结束同一段(关掉 / 列清单发现没了),只算先到的
            row = self.repo.get_span(span_id)
            if row is None or row["end_time_unix_nano"] is not None:
                return False
            attrs = _kvs(attributes) + kvs({"memorytalk.end.user.id": user})
            self.repo.update_span(span_id, end_time_unix_nano=self.clock() if at is None else at, status_code=status,
                                  end_user_id=user, attributes=_merge(row["attributes"] or [], attrs), seq=self.repo.next_seq())
        self.changes.notify()
        return True

    def point(self, work_id: str, span_id: str | None, event_name: str, attributes: dict | list, *, user: str | None = None,
              worklet_id: str | None = None, column_number: int | None = None, body: str | None = None,
              uid: str | None = None, at: int | None = None, trace_id: str | None = None) -> bool:
        """追加一行点;带 uid 的已经有了就跳过。at = 这件事发生的时刻(不给 = 现在),收到的时刻另记。交回这次写没写。"""
        trace_id = trace_id or self.trace_id(work_id)
        now = self.clock()
        with self.repo.tx():
            if uid is not None and self.repo.has_point(uid):
                return False
            self.repo.insert_point({
                "seq": self.repo.next_seq(), "uid": uid, "trace_id": trace_id, "span_id": span_id,
                "work_id": work_id, "worklet_id": worklet_id, "column_number": column_number, "user_id": user,
                "event_name": event_name, "time_unix_nano": now if at is None else at, "observed_time_unix_nano": now,
                "body": body, "attributes": kvs({"user.id": user}) + _kvs(attributes)})
        self.changes.notify()
        return True

    # ================================================================ 谁挂在谁下面

    def trace_id(self, work_id: str) -> str:
        return trace_id_of(self.tree.root_of(work_id))

    def work_span(self, work_id: str | None) -> str | None:
        """这个 work 最新的一段 work 段(根的父 = None)。"""
        if not work_id:
            return None
        spans = self.repo.work_spans(work_id)
        return spans[-1]["span_id"] if spans else None

    def worklet_span(self, worklet_id: str) -> dict | None:
        """这个工作单元最新的一段 worklet 段。"""
        spans = self.repo.worklet_spans(worklet_id)
        return spans[-1] if spans else None

    # ================================================================ work 段:建 → 归档;重新打开 = 新的一段

    def work_started(self, work: Work, user: str | None, *, archived_at: int | None = None) -> None:
        """建 work 开第 0 段;重新打开开新的一段,link 指向上一段。archived_at = 上一次归档的时刻(重新打开时给)。"""
        trace_id = self.trace_id(work.id)
        with self.repo.tx():
            segments = self.repo.work_spans(work.id)
            if segments:
                self._archived_late(work.id, archived_at)
            prev = segments[-1]["span_id"] if segments else None
            attrs = {"memorytalk.work.id": work.id, "memorytalk.work.goal": work.goal}
            if prev:
                attrs["memorytalk.work.reopened"] = True
            self.start(work.id, "work", work_span_id(work.id, len(segments)), self.work_span(work.parent), attrs,
                       user=user, links=[prev] if prev else (), trace_id=trace_id)

    def work_archived(self, work_id: str, user: str | None, columns: dict[str, Column | None]) -> None:
        """归档:开着的工作单元段先结束(reason archived),再结束 work 段。columns = 工作单元此刻在哪一列。
        结束的是所有还开着的 work 段,不只最新的一段(正常只有一段开着;万一多了,也不留一段永远开着)。"""
        for s in self.repo.open_spans(work_id, "worklet"):
            self.worklet_ended(s["span_id"], "archived", user, columns.get(s["worklet_id"]))
        for s in self.repo.open_spans(work_id, "work"):
            self.end(s["span_id"], {"memorytalk.end.reason": "archived"}, user=user)

    def _archived_late(self, work_id: str, archived_at: int | None) -> None:
        """重新打开时上一次归档还有段开着(那次轨迹没写进去):按归档补上终点(reason archived,终点取归档的时刻,
        不早于段的起点;不知道是谁归档的,不记人)——一个 work 同时只有一段 work 段开着,上一段里的工作单元段也不跨过去。"""
        for s in self.repo.open_spans(work_id, "worklet") + self.repo.open_spans(work_id, "work"):
            at = max(archived_at, s["start_time_unix_nano"]) if archived_at is not None else None
            if s["name"] == "worklet":
                self.worklet_ended(s["span_id"], "archived", None, None, at=at)
            else:
                self.end(s["span_id"], {"memorytalk.end.reason": "archived"}, at=at)

    def work_renamed(self, work_id: str, goal: str, before: str, user: str | None) -> None:
        self.point(work_id, self.work_span(work_id), "work.renamed", {"memorytalk.work.goal": goal, "memorytalk.from": before}, user=user)

    # ================================================================ worklet 段:打开 → 关掉 / 归档 / 现场没了

    def worklet_started(self, work_id: str, m: Worklet, column: Column | None, user: str | None, *, resume: bool = False) -> None:
        """resume = 重入:段还开着就不再开,结束了(现场没了 / 归档过)才开新的一段。"""
        trace_id = self.trace_id(work_id)
        with self.repo.tx():
            spans = self.repo.worklet_spans(m.id)
            if resume and spans and spans[-1]["end_time_unix_nano"] is None:
                return
            attrs = {"memorytalk.work.id": work_id, "memorytalk.worklet.id": m.id, "memorytalk.worklet.uri": m.uri,
                     "memorytalk.worklet.scheme": m.scheme, "memorytalk.worklet.server": m.server, **_col("memorytalk.", column)}
            self.start(work_id, "worklet", worklet_span_id(m.id, len(spans)), self.work_span(work_id), attrs,
                       user=user, worklet_id=m.id, trace_id=trace_id)

    def worklet_closed(self, work_id: str, worklet_id: str, column: Column | None, user: str | None) -> None:
        """关掉的时候它已经没有开着的段了(现场没了 / 归档过又重新打开、还没重入):段不再动,
        在它最新的一段 worklet 段上打一个 worklet.closed 点,记下谁在哪一列关的。"""
        span = self.worklet_span(worklet_id)
        self.point(work_id, span["span_id"] if span else self.work_span(work_id), "worklet.closed",
                   {"memorytalk.worklet.id": worklet_id, **_col("memorytalk.", column)},
                   user=user, worklet_id=worklet_id, column_number=_number(column))

    def open_worklet_span(self, worklet_id: str) -> str | None:
        s = self.worklet_span(worklet_id)
        return s["span_id"] if s and s["end_time_unix_nano"] is None else None

    def worklet_ended(self, span_id: str, reason: str, user: str | None, column: Column | None,
                      status: int = STATUS_OK, at: int | None = None) -> bool:
        """结束 worklet 段;里面还开着的 agent 段跟着结束(原因、status 同 worklet 段)。"""
        ended = self.end(span_id, {"memorytalk.end.reason": reason, **_col("memorytalk.end.", column)}, status=status, user=user, at=at)
        try:                                                 # 收尾失败不挡后面的(归档时还要接着结束别的段和 work 段)
            if row := self.repo.get_span(span_id):
                self.turns(row["work_id"], row["worklet_id"])
                self.agent_ended(row["worklet_id"], reason, status)
        except Exception:
            log.exception("agent 段没收尾:%s", span_id)
        return ended

    def agent_ended(self, worklet_id: str, reason: str, status: int) -> None:
        """worklet 段结束了,里面还开着的会话 / 轮次 / 工具段跟着结束:原因、status 同 worklet 段,终点取它里面最后一次动静
        (最后一个点、子段的终点,都没有就是它的起点)。正常由节点 flush 时先结束好,这里只兜底(节点没起来、flush 超时)。"""
        rank = {"agent.tool": 0, "agent.turn": 1, "agent.session": 2}          # 先里层,子段先于父段结束
        for s in sorted(self.repo.open_agent_spans(worklet_id), key=lambda s: rank.get(s["name"], 3)):
            last = [s["start_time_unix_nano"], self.repo.last_point_time(s["span_id"]) or 0]
            last += [c["end_time_unix_nano"] or c["start_time_unix_nano"] for c in self.repo.children(worklet_id, s["span_id"])]
            self.end(s["span_id"], {"memorytalk.end.reason": reason}, status=status, at=max(last))

    # ================================================================ 节点推上来的(POST /works/{id}/trace)

    def ingest(self, work_id: str, doc: dict, cursors: Sequence[dict] = (), *,
               gone: Callable[[str], dict | None] | None = None) -> dict:
        """收一批 OTLP/JSON(和 GET 读出来的一个形状),外加推到哪了。先整批验(越界 403、不成形 422),再一个事务写完:
        段按 spanId(没有就插;开着的,带终点就结束、不带就合并属性;结束了的跳过),点按 log.record.uid(有了就跳过)。
        节点只能写它的工作单元的 agent.* 段和点,以及给 worklet 段补一个 gone 结束。
        gone(worklet id) → 补进 worklet 段结束属性的东西(结束那一刻在哪一列,中心才知道);交回 None = 这条 gone 不收
        (正在关 / 归档 / 重入,或者现场其实还活着)。"""
        trace_id = self.trace_id(work_id)
        owned: dict[str, bool] = {}

        def check_worklet(worklet_id) -> str:
            if not isinstance(worklet_id, str) or not worklet_id:
                raise TraceRejected(422, "缺 memorytalk.worklet.id")
            if worklet_id not in owned:
                owned[worklet_id] = any(r["work_id"] == work_id for r in self.repo.worklet_spans(worklet_id))
            if not owned[worklet_id]:
                raise TraceRejected(422, f"{worklet_id} 不是 {work_id} 的工作单元")
            return worklet_id

        spans = [self._check_span(work_id, trace_id, s, check_worklet) for s in _items(doc, "traces", "resourceSpans", "scopeSpans", "spans")]
        points = [self._check_point(trace_id, r, check_worklet) for r in _items(doc, "logs", "resourceLogs", "scopeLogs", "logRecords")]
        for c in cursors:
            check_worklet(c.get("worklet_id"))
            if not isinstance(c.get("source"), str) or not isinstance(c.get("position"), str):
                raise TraceRejected(422, "cursors 要有 worklet_id / source / position(字符串)")
        for s in spans:                                              # 要读 works.db 的,在事务外先算好
            if s["name"] == "worklet" and gone:
                more = gone(s["worklet_id"])
                s["skip"] = more is None
                s["attributes"] = s["attributes"] + _kvs(more)
        out = {"spans": {"inserted": 0, "ended": 0, "merged": 0, "ignored": 0}, "points": {"inserted": 0, "duplicate": 0}}
        with self.repo.tx():
            for s in spans:
                out["spans"][self._apply_span(work_id, trace_id, s)] += 1
            for p in points:
                written = self.point(work_id, p["span_id"], p["event"], p["attributes"], worklet_id=p["worklet_id"],
                                     body=p["body"], uid=p["uid"], at=p["time"], trace_id=trace_id)
                out["points"]["inserted" if written else "duplicate"] += 1
            for c in cursors:
                self.repo.put_cursor(c["worklet_id"], c["source"], c["position"], self.clock())
        return out

    def _check_span(self, work_id: str, trace_id: str, s: dict, check_worklet) -> dict:
        name = s.get("name")
        attrs = [kv for kv in s.get("attributes") or [] if kv.get("key") != "memorytalk.open"]   # 读出来的「开着」标记,写回来不算数
        end = _nanos(s.get("endTimeUnixNano"), "endTimeUnixNano", optional=True)
        span_id = s.get("spanId")
        if not isinstance(span_id, str) or len(span_id) != 16 or not _HEX.fullmatch(span_id):
            raise TraceRejected(422, f"spanId 要是 16 位十六进制:{span_id!r}")
        if s.get("traceId") != trace_id:
            raise TraceRejected(422, f"{span_id} 的 traceId 不是 {work_id} 这棵树的")
        if name == "worklet":                                        # 只能补一个 gone 结束,开、别的结束都归中心
            row = self.repo.get_span(span_id)
            if end is None or attr(attrs, "memorytalk.end.reason") != "gone":
                raise TraceRejected(403, "worklet 段只能由节点补一个 gone 结束")
            if row is None or row["name"] != "worklet" or row["work_id"] != work_id:
                raise TraceRejected(422, f"{span_id} 不是 {work_id} 的 worklet 段")
            return {"name": name, "span_id": span_id, "end": end, "attributes": attrs, "status": _status(s),
                    "worklet_id": row["worklet_id"]}
        if name not in AGENT_SPANS:
            raise TraceRejected(403, f"节点不能写 {name!r} 段")
        parent = s.get("parentSpanId") or None
        return {"name": name, "span_id": span_id, "parent": parent, "kind": int(s.get("kind") or KIND_INTERNAL),
                "start": _nanos(s.get("startTimeUnixNano"), "startTimeUnixNano"), "end": end, "status": _status(s),
                "attributes": attrs, "links": list(s.get("links") or []),
                "worklet_id": check_worklet(attr(attrs, "memorytalk.worklet.id"))}

    def _check_point(self, trace_id: str, r: dict, check_worklet) -> dict:
        event = r.get("eventName")
        if event not in AGENT_POINTS:
            raise TraceRejected(403, f"节点不能写 {event!r} 点")
        attrs = list(r.get("attributes") or [])
        uid = attr(attrs, "log.record.uid")
        if not isinstance(uid, str) or not uid:
            raise TraceRejected(422, "节点推的点要带 log.record.uid")
        if r.get("traceId", trace_id) != trace_id:
            raise TraceRejected(422, f"{uid} 的 traceId 不是这棵树的")
        body = r.get("body")
        if isinstance(body, dict):
            body = body["stringValue"] if "stringValue" in body else json.dumps(body, ensure_ascii=False)
        return {"event": event, "uid": uid, "span_id": r.get("spanId") or None, "time": _nanos(r.get("timeUnixNano"), "timeUnixNano"),
                "body": body if isinstance(body, str) else None, "attributes": attrs,
                "worklet_id": check_worklet(attr(attrs, "memorytalk.worklet.id"))}

    def _apply_span(self, work_id: str, trace_id: str, s: dict) -> str:
        if s["name"] == "worklet":                                   # 现场没了:节点报的 gone
            if s.get("skip"):
                return "ignored"
            return "ended" if self._worklet_gone(s["span_id"], s["attributes"], s["end"], s["status"]) else "ignored"
        row = self.repo.get_span(s["span_id"])
        if row is None:
            self.start(work_id, s["name"], s["span_id"], s["parent"], s["attributes"], worklet_id=s["worklet_id"],
                       links=s["links"], at=s["start"], trace_id=trace_id, kind=s["kind"])
            if s["end"] is not None:
                self.end(s["span_id"], status=s["status"], at=s["end"])
            return "inserted"
        if row["end_time_unix_nano"] is not None:                    # 结束即定稿
            return "ignored"
        if s["end"] is not None:
            return "ended" if self.end(s["span_id"], s["attributes"], status=s["status"], at=s["end"]) else "ignored"
        return "merged" if self.merge(s["span_id"], s["attributes"]) else "ignored"

    def _worklet_gone(self, span_id: str, attrs: list[dict], at: int, status: int) -> bool:
        ended = self.end(span_id, attrs, status=status, at=at)
        if ended and (row := self.repo.get_span(span_id)):
            self.agent_ended(row["worklet_id"], "gone", status)
        return ended

    def cursors(self, worklet_id: str) -> list[dict]:
        return [{"worklet_id": r["worklet_id"], "source": r["source"], "position": r["position"],
                 "updated_at": str(r["updated_at"])} for r in self.repo.cursors_of(worklet_id)]

    # ================================================================ agent.turn 段(旧的拉取路径:Codex / Kimi 的 round 切出来)

    def turns(self, work_id: str, worklet_id: str) -> None:
        """按 worktrace.db 里这个工作单元的 round 重切一遍轮次,按第一条 round 幂等写:没有就插,终点 / 属性 / status 变了就改。
        不记人(轮次是 agent 的,不是读 round 的那个人的)。worklet 段已经结束了(关掉 / 归档 / 现场没了),开着的轮次跟着结束,
        status 同 worklet 段;结束了的轮次不再打开——之后又同步进来的 round 只把终点挪到它最后一条 round 的时刻。"""
        seg = self.worklet_span(worklet_id)                  # 挂在它最新的一段 worklet 段下;trace id 跟着它
        trace_id = seg["trace_id"] if seg else self.trace_id(work_id)
        closing = seg is not None and seg["end_time_unix_nano"] is not None
        server = attr((seg or {}).get("attributes"), "memorytalk.worklet.server")
        system = GEN_AI_SYSTEM.get(server)
        with self.repo.tx():
            turns = slice_turns([Round(id=r["round_id"], timestamp=r["timestamp"], role=r["role"], text="")
                                 for r in self.repo.read_rounds(worklet_id)])
            have = {s["first_round_id"]: s for s in self.repo.turn_spans(worklet_id)} if turns else {}
            changed = False
            for t in turns:
                old = have.get(t.first)
                was_closed = old is not None and old["end_time_unix_nano"] is not None
                if t.closed:
                    end, status = t.last_at, STATUS_OK
                elif was_closed:
                    end, status = t.last_at, old["status_code"]
                elif closing:
                    end, status = t.last_at, seg["status_code"]
                else:
                    end, status = None, STATUS_UNSET
                attrs = {"memorytalk.worklet.id": worklet_id, "memorytalk.round.first": t.first, "memorytalk.round.last": t.last,
                         "memorytalk.round.count": t.count, "gen_ai.system": system}
                if old is None:
                    span_id = turn_span_id(worklet_id, t.first)
                    self.start(work_id, "agent.turn", span_id, seg["span_id"] if seg else None,
                               attrs, worklet_id=worklet_id, at=t.start, first_round_id=t.first, trace_id=trace_id)
                    if end is not None:
                        self.repo.update_span(span_id, end_time_unix_nano=end, status_code=status, seq=self.repo.next_seq())
                        changed = True
                    continue
                row = {"end_time_unix_nano": end, "status_code": status, "attributes": kvs(attrs)}
                if changes := {k: v for k, v in row.items() if old[k] != v}:
                    self.repo.update_span(old["span_id"], **changes, seq=self.repo.next_seq())
                    changed = True
        if changed:
            self.changes.notify()

    # ================================================================ 点

    def column_changed(self, work_id: str, event: str, column: Column, user: str | None, **extra) -> None:
        """column.added / column.renamed / column.removed,挂在 work 段上。"""
        self.point(work_id, self.work_span(work_id), event, {**_col("memorytalk.", column), **extra},
                   user=user, column_number=_number(column))

    def worklet_moved(self, work_id: str, worklet_id: str, src: tuple[Column, int], dst: tuple[Column, int], user: str | None) -> None:
        span = self.worklet_span(worklet_id)
        (a, i), (b, j) = src, dst
        attrs = {"memorytalk.worklet.id": worklet_id, **_col("memorytalk.", b), "memorytalk.index": j,
                 **_col("memorytalk.from.", a), "memorytalk.from.index": i}
        self.point(work_id, span["span_id"] if span else self.work_span(work_id), "worklet.moved", attrs,
                   user=user, worklet_id=worklet_id, column_number=_number(b))

    # ================================================================ 读:OTLP/JSON

    def read(self, work_ids: Sequence[str], *, worklet: str | None = None, agent: bool = False, bodies: bool = False,
             after: int | None = None) -> dict:
        """段和点(默认不带 agent 那几层、不带正文);after = 只要这个变更序号之后写的或改过的。
        seq = 读的这一刻这几个 work 最大的变更序号,下次带着它来接着读。一次读是一个快照(持着库的锁)。"""
        with self.repo.tx():
            seq = self.repo.max_seq(work_ids)
            spans = [self._span(r) for r in self.repo.spans_of(work_ids, worklet=worklet, agent=agent, after=after)]
            logs = [self._log(r, bodies) for r in self.repo.points_of(work_ids, worklet=worklet, agent=agent, after=after)]
        return {"traces": {"resourceSpans": [{"resource": self.resource, "scopeSpans": [{"scope": SCOPE, "spans": spans}]}]},
                "logs": {"resourceLogs": [{"resource": self.resource, "scopeLogs": [{"scope": SCOPE, "logRecords": logs}]}]},
                "seq": str(max(seq, after or 0))}

    def changed_since(self, work_ids: Sequence[str], after: int, *, worklet: str | None = None, agent: bool = False) -> bool:
        """after 之后有没有这次读会读到的新东西(长轮询醒来先问这个)。"""
        return bool(self.repo.spans_of(work_ids, worklet=worklet, agent=agent, after=after, limit=1)
                    or self.repo.points_of(work_ids, worklet=worklet, agent=agent, after=after, limit=1))

    @staticmethod
    def _span(r: dict) -> dict:
        out = {"traceId": r["trace_id"], "spanId": r["span_id"]}
        if r["parent_span_id"]:
            out["parentSpanId"] = r["parent_span_id"]
        out.update(name=r["name"], kind=r["kind"], startTimeUnixNano=str(r["start_time_unix_nano"]))
        attrs = list(r["attributes"] or [])
        if r["end_time_unix_nano"] is None:
            attrs += kvs({"memorytalk.open": True})              # 开着的段:没有终点(OTLP 没有「开着」这回事,我们自己标一下)
        else:
            out["endTimeUnixNano"] = str(r["end_time_unix_nano"])
        out.update(attributes=attrs, links=r["links"] or [], status={"code": r["status_code"]})
        return out

    @staticmethod
    def _log(r: dict, bodies: bool = False) -> dict:
        t = str(r["time_unix_nano"])
        observed = r.get("observed_time_unix_nano")
        out = {"timeUnixNano": t, "observedTimeUnixNano": str(observed) if observed is not None else t,
               "eventName": r["event_name"], "traceId": r["trace_id"]}
        if r["span_id"]:
            out["spanId"] = r["span_id"]
        if bodies and r.get("body") is not None:
            out["body"] = {"stringValue": r["body"]}
        out["attributes"] = r["attributes"] or []
        return out


def _items(doc: dict, top: str, resources: str, scopes: str, items: str) -> list[dict]:
    """OTLP/JSON 里一层层拆出段(或点)来;形状不对就 422。"""
    try:
        return [x for res in ((doc.get(top) or {}).get(resources) or []) for sc in (res.get(scopes) or [])
                for x in (sc.get(items) or [])]
    except AttributeError:
        raise TraceRejected(422, f"{top} 不是 OTLP/JSON") from None


def _nanos(v, field: str, *, optional: bool = False) -> int | None:
    """OTLP/JSON 的 64 位整数是十进制字符串(也收整数)。"""
    if v is None and optional:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise TraceRejected(422, f"{field} 要是 Unix 纳秒:{v!r}") from None
    if n < 0:
        raise TraceRejected(422, f"{field} 不能是负的")
    return n


def _status(s: dict) -> int:
    code = (s.get("status") or {}).get("code", STATUS_UNSET)
    if code not in (STATUS_UNSET, STATUS_OK, STATUS_ERROR):
        raise TraceRejected(422, f"status.code 只能是 0 / 1 / 2:{code!r}")
    return code
