"""轨迹:有起止的记成段(span),一个时刻的事记成点(log record)。字段和 OTel 一对一,落在 worktrace.db(docs/designs/v5/work-trace.md)。

只有三个动作:start(插一行段,终点为空)、end(同一行补上终点)、point(追加一行点)。id 由身份算出来:
一棵 work 树是一条 trace(trace id 由根 work 算),work / worklet 段的 id 由「谁 + 第几段」算,不用查也知道该挂在谁下面;
agent 轮次(agent.turn)由同步进来的 round 切出来(turns.py),id 由它第一条 round 算,再同步一次按它幂等改。
对外(GET /works/{id}/trace)拼成 OTLP/JSON 的 TracesData + LogsData。
写入顺序是先 works.db、后这里;这里写失败不回滚 work,由 WorkService 兜住只记日志。
「查一下再写」的几处(第几段、还开着没有)包在 worktrace.db 的事务里;要读 works.db 的(trace id 要走到根)在事务外先算好,
两把锁只会按「worktrace → works」或单独一把的顺序拿。
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Callable, Sequence

from memorytalk.backend.models.work import Column, Round, Work, Worklet

from .repo import TraceRepo
from .tree import WorkTree
from .turns import slice_turns

KIND_INTERNAL = 1
STATUS_UNSET, STATUS_OK = 0, 1
SCOPE = {"name": "memorytalk.work", "version": "5"}
GEN_AI_SYSTEM = {"claude": "anthropic", "codex": "openai", "kimi": "moonshot"}     # server → OTel GenAI 的 gen_ai.system

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
    """agent 轮次的 id 由它的第一条 round 算:同一轮再同步一次还是同一个 id。"""
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


class Trace:
    def __init__(self, repo: TraceRepo, tree: WorkTree, clock: Callable[[], int] = time.time_ns) -> None:
        self.repo = repo
        self.tree = tree
        self.clock = clock
        self.resource = {"attributes": kvs({"service.name": "memory.talk"})}

    # ================================================================ 三个动作

    def start(self, work_id: str, name: str, span_id: str, parent_span_id: str | None, attributes: dict, *,
              user: str | None = None, worklet_id: str | None = None, links: Sequence[str] = (),
              at: int | None = None, first_round_id: str | None = None, trace_id: str | None = None) -> str:
        trace_id = trace_id or self.trace_id(work_id)
        self.repo.insert_span({
            "span_id": span_id, "trace_id": trace_id, "parent_span_id": parent_span_id,
            "work_id": work_id, "worklet_id": worklet_id, "user_id": user, "end_user_id": None,
            "name": name, "kind": KIND_INTERNAL,
            "start_time_unix_nano": self.clock() if at is None else at, "end_time_unix_nano": None,
            "status_code": STATUS_UNSET, "attributes": kvs({**attributes, "user.id": user}),
            "links": [{"traceId": trace_id, "spanId": s, "attributes": []} for s in links],
            "first_round_id": first_round_id})
        return span_id

    def end(self, span_id: str, attributes: dict | None = None, *, status: int = STATUS_OK,
            user: str | None = None, at: int | None = None) -> bool:
        """在同一行补上终点和结束时的属性;已经结束的不再动。交回这次有没有结束它。"""
        with self.repo.tx():                            # 两处同时结束同一段(关掉 / 列清单发现没了),只算先到的
            row = self.repo.get_span(span_id)
            if row is None or row["end_time_unix_nano"] is not None:
                return False
            attrs = {**(attributes or {}), "memorytalk.end.user.id": user}
            self.repo.update_span(span_id, end_time_unix_nano=self.clock() if at is None else at, status_code=status,
                                  end_user_id=user, attributes=_merge(row["attributes"] or [], kvs(attrs)))
            return True

    def point(self, work_id: str, span_id: str | None, event_name: str, attributes: dict, *, user: str | None = None,
              worklet_id: str | None = None, column_number: int | None = None) -> None:
        self.repo.insert_point({
            "trace_id": self.trace_id(work_id), "span_id": span_id, "work_id": work_id, "worklet_id": worklet_id,
            "column_number": column_number, "user_id": user, "event_name": event_name,
            "time_unix_nano": self.clock(), "attributes": kvs({"user.id": user, **attributes})})

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
        """结束 worklet 段;里面还开着的 agent 轮次跟着结束(终点 = 那一轮最后一条 round 的时刻,status 同 worklet 段)。"""
        ended = self.end(span_id, {"memorytalk.end.reason": reason, **_col("memorytalk.end.", column)}, status=status, user=user, at=at)
        try:                                                 # 轮次收尾失败不挡后面的(归档时还要接着结束别的段和 work 段)
            if row := self.repo.get_span(span_id):
                self.turns(row["work_id"], row["worklet_id"])
        except Exception:
            log.exception("agent 轮次没收尾:%s", span_id)
        return ended

    # ================================================================ agent.turn 段:从 round 切出来(turns.py)

    def turns(self, work_id: str, worklet_id: str) -> None:
        """按 worktrace.db 里这个工作单元的 round 重切一遍轮次,按第一条 round 幂等写:没有就插,终点 / 属性 / status 变了就改。
        不记人(轮次是 agent 的,不是读 round 的那个人的)。worklet 段已经结束了(关掉 / 归档 / 现场没了),开着的轮次跟着结束,
        status 同 worklet 段;结束了的轮次不再打开——之后又同步进来的 round 只把终点挪到它最后一条 round 的时刻。"""
        seg = self.worklet_span(worklet_id)                  # 挂在它最新的一段 worklet 段下;trace id 跟着它
        trace_id = seg["trace_id"] if seg else self.trace_id(work_id)
        closing = seg is not None and seg["end_time_unix_nano"] is not None
        server = next((kv["value"].get("stringValue") for kv in (seg or {}).get("attributes") or []
                       if kv["key"] == "memorytalk.worklet.server"), None)
        system = GEN_AI_SYSTEM.get(server)
        with self.repo.tx():
            turns = slice_turns([Round(id=r["round_id"], timestamp=r["timestamp"], role=r["role"], text="")
                                 for r in self.repo.read_rounds(worklet_id)])
            have = {s["first_round_id"]: s for s in self.repo.turn_spans(worklet_id)} if turns else {}
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
                    span_id = self.start(work_id, "agent.turn", turn_span_id(worklet_id, t.first), seg["span_id"] if seg else None,
                                         attrs, worklet_id=worklet_id, at=t.start, first_round_id=t.first, trace_id=trace_id)
                    if end is not None:
                        self.repo.update_span(span_id, end_time_unix_nano=end, status_code=status)
                    continue
                row = {"end_time_unix_nano": end, "status_code": status, "attributes": kvs(attrs)}
                if changes := {k: v for k, v in row.items() if old[k] != v}:
                    self.repo.update_span(old["span_id"], **changes)

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

    def read(self, work_ids: Sequence[str]) -> dict:
        spans = [self._span(r) for r in self.repo.spans_of(work_ids)]
        logs = [self._log(r) for r in self.repo.points_of(work_ids)]
        return {"traces": {"resourceSpans": [{"resource": self.resource, "scopeSpans": [{"scope": SCOPE, "spans": spans}]}]},
                "logs": {"resourceLogs": [{"resource": self.resource, "scopeLogs": [{"scope": SCOPE, "logRecords": logs}]}]}}

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
    def _log(r: dict) -> dict:
        t = str(r["time_unix_nano"])
        out = {"timeUnixNano": t, "observedTimeUnixNano": t, "eventName": r["event_name"], "traceId": r["trace_id"]}
        if r["span_id"]:
            out["spanId"] = r["span_id"]
        out["attributes"] = r["attributes"] or []
        return out
