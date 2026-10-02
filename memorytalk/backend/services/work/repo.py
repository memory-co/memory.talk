"""work 的仓储:两个 sqlite——works.db 管现在,worktrace.db 管经过(docs/designs/v5/work-store.md)。

一张表一种东西,一行一个实体,要查、要单独改的都是真的列。这里每个方法就是一两条语句;
一个动作要改的几处,由上面的 helper(tree / columns / worklets / inbox)包在一个 `tx()` 里。不写 SQL,走 provider 的链式查询。
"""
from __future__ import annotations

from typing import Sequence

from memorytalk.backend.providers import Column, DatabaseProvider
from memorytalk.backend.providers.db import JSON


# ================================================================ works.db:现在

class WorkRepo:
    """works(节点 + 计数器 + 谁在看)/ work_columns(列)/ worklets(登记 + 摆在哪一列哪个位置)/ inbox(收件箱)。"""

    def __init__(self, db: DatabaseProvider) -> None:
        self.db = db
        self.works = db.table(
            "works",
            Column("id", str, primary=True), Column("parent", str, index=True), Column("goal", str), Column("status", str),
            Column("created_by", str, index=True), Column("created_at", str), Column("archived_at", str),
            Column("manager", str), Column("viewers", JSON),
            Column("next_worklet", int), Column("next_column", int))
        self.work_columns = db.table(
            "work_columns",
            Column("work_id", str), Column("number", int), Column("alias", str), Column("collapsed", bool), Column("position", int),
            primary_key=("work_id", "number"), indexes=[("work_id", "position")])
        self.worklets = db.table(
            "worklets",
            Column("id", str, primary=True), Column("work_id", str, index=True), Column("number", int),
            Column("uri", str), Column("scheme", str), Column("server", str), Column("cwd", str),
            Column("created_at", str), Column("last_attached", str),
            Column("column_number", int), Column("position", int), Column("collapsed", bool),
            indexes=[("work_id", "column_number", "position")])       # 不做 UNIQUE:sqlite 在 position + 1 的过程中逐行查重
        self.inbox = db.table(
            "inbox",
            Column("seq", int, primary=True, autoincrement=True), Column("work_id", str, index=True),
            Column("ts", str), Column("layer", str), Column("path", str), Column("subject", str),
            Column("sha", str), Column("by", str), Column("routed_by", str))

    def tx(self):
        """一个动作 = 一个事务(持着 provider 的锁)。里面不做建现场 / 销毁现场,也不写 worktrace.db。"""
        return self.db.transaction()

    # ---- works ----

    def get_work(self, work_id: str) -> dict | None:
        return self.db.select(self.works).where(self.works.c.id == work_id).one()

    def list_works(self, *, created_by: str | None = None) -> list[dict]:
        q = self.db.select(self.works)
        if created_by is not None:
            q = q.where(self.works.c.created_by == created_by)
        return q.order_by(self.works.c.id.asc()).all()

    def children(self, work_id: str) -> list[dict]:
        return self.db.select(self.works).where(self.works.c.parent == work_id).order_by(self.works.c.id.asc()).all()

    def insert_work(self, row: dict) -> None:
        """新 work:节点一行 + 第一列(编号 1);计数器从头开始。"""
        with self.tx():
            self.db.insert(self.works).values(**row, manager=None, viewers=[], next_worklet=1, next_column=2).run()
            self.db.insert(self.work_columns).values(work_id=row["id"], number=1, alias="", collapsed=False, position=0).run()

    def update_work(self, work_id: str, **changes) -> None:
        """只改给的那几列(goal / status / archived_at / manager),计数器和 viewers 不碰。"""
        self.db.update(self.works).where(self.works.c.id == work_id).set(**changes).run()

    def _take(self, work_id: str, counter: str) -> int:
        with self.tx():
            n = self.get_work(work_id)[counter]
            self.db.update(self.works).where(self.works.c.id == work_id).set(**{counter: getattr(self.works.c, counter) + 1}).run()
            return n

    def take_worklet_number(self, work_id: str) -> int:
        """取下一个工作单元编号并 +1:单调递增,建现场失败这个号也不还。"""
        return self._take(work_id, "next_worklet")

    def take_column_number(self, work_id: str) -> int:
        return self._take(work_id, "next_column")

    def set_viewers(self, work_id: str, names: list[str]) -> None:
        """viewers 只整份写(由内存里的心跳表算出来),不读出来追加。"""
        self.db.update(self.works).where(self.works.c.id == work_id).set(viewers=names).run()

    def clear_viewers(self) -> None:
        """重启那一刻谁也没在看。"""
        with self.tx():
            for w in self.db.select(self.works).all():
                if w["viewers"]:
                    self.set_viewers(w["id"], [])

    # ---- work_columns:列,position 从左到右 0..n-1 ----

    def list_columns(self, work_id: str) -> list[dict]:
        t = self.work_columns
        return self.db.select(t).where(t.c.work_id == work_id).order_by(t.c.position.asc()).all()

    def get_column(self, work_id: str, number: int) -> dict | None:
        t = self.work_columns
        return self.db.select(t).where(t.c.work_id == work_id, t.c.number == number).one()

    def insert_column(self, work_id: str, number: int, alias: str, position: int) -> None:
        self.db.insert(self.work_columns).values(work_id=work_id, number=number, alias=alias, collapsed=False, position=position).run()

    def update_column(self, work_id: str, number: int, **changes) -> None:
        t = self.work_columns
        self.db.update(t).where(t.c.work_id == work_id, t.c.number == number).set(**changes).run()

    def delete_column(self, work_id: str, number: int) -> None:
        t = self.work_columns
        self.db.delete(t).where(t.c.work_id == work_id, t.c.number == number).run()

    def shift_columns(self, work_id: str, from_position: int, delta: int) -> None:
        """position ≥ from_position 的列整体挪 delta(插列 +1,删列 −1)。"""
        t = self.work_columns
        self.db.update(t).where(t.c.work_id == work_id, t.c.position >= from_position).set(position=t.c.position + delta).run()

    # ---- worklets:登记 + 摆在哪(column_number 为空 = 不在任何一列)----

    def list_worklets(self, work_id: str) -> list[dict]:
        """按开的先后(编号)排。"""
        t = self.worklets
        return self.db.select(t).where(t.c.work_id == work_id).order_by(t.c.number.asc()).all()

    def get_worklet(self, work_id: str, worklet_id: str) -> dict | None:
        t = self.worklets
        return self.db.select(t).where(t.c.id == worklet_id, t.c.work_id == work_id).one()

    def column_worklets(self, work_id: str, number: int) -> list[dict]:
        t = self.worklets
        return self.db.select(t).where(t.c.work_id == work_id, t.c.column_number == number).order_by(t.c.position.asc()).all()

    def insert_worklet(self, row: dict) -> None:
        self.db.insert(self.worklets).values(**row).run()

    def update_worklet(self, worklet_id: str, **changes) -> None:
        self.db.update(self.worklets).where(self.worklets.c.id == worklet_id).set(**changes).run()

    def delete_worklet(self, worklet_id: str) -> None:
        self.db.delete(self.worklets).where(self.worklets.c.id == worklet_id).run()

    def shift_worklets(self, work_id: str, number: int, from_position: int, delta: int, *, skip: str | None = None) -> None:
        """某一列里 position ≥ from_position 的工作单元整体挪 delta;skip = 正在挪的那个自己不动。"""
        t = self.worklets
        conds = [t.c.work_id == work_id, t.c.column_number == number, t.c.position >= from_position]
        if skip is not None:
            conds.append(t.c.id != skip)
        self.db.update(t).where(*conds).set(position=t.c.position + delta).run()

    # ---- inbox:work_id 为空 = 没人管 ----

    def put_inbox(self, work_id: str | None, item: dict) -> None:
        self.db.insert(self.inbox).values(work_id=work_id, **item).run()

    def read_inbox(self, work_id: str) -> list[dict]:
        t = self.inbox
        return [_item(r) for r in self.db.select(t).where(t.c.work_id == work_id).order_by(t.c.seq.asc()).all()]

    def read_unmanaged(self) -> list[dict]:
        t = self.inbox
        return [_item(r) for r in self.db.select(t).where(t.c.work_id.is_null()).order_by(t.c.seq.asc()).all()]


def _item(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in ("seq", "work_id")}


# ================================================================ worktrace.db:经过

class TraceRepo:
    """spans(段;end_time_unix_nano 为空 = 还开着)/ points(点,只追加)/ rounds(agent 的 round,只追加)。
    列和 OTLP 字段一对一:id 是十六进制串,时间是 Unix 纳秒整数,attributes / links 是 OTLP 的 JSON。"""

    def __init__(self, db: DatabaseProvider) -> None:
        self.db = db
        self.spans = db.table(
            "spans",
            Column("span_id", str, primary=True), Column("trace_id", str, index=True), Column("parent_span_id", str),
            Column("work_id", str, index=True), Column("worklet_id", str, index=True),
            Column("user_id", str, index=True), Column("end_user_id", str, index=True),
            Column("name", str), Column("kind", int),
            Column("start_time_unix_nano", int), Column("end_time_unix_nano", int), Column("status_code", int),
            Column("attributes", JSON), Column("links", JSON), Column("first_round_id", str))
        self.points = db.table(
            "points",
            Column("seq", int, primary=True, autoincrement=True), Column("trace_id", str), Column("span_id", str, index=True),
            Column("work_id", str, index=True), Column("worklet_id", str), Column("column_number", int),
            Column("user_id", str, index=True), Column("event_name", str, index=True),
            Column("time_unix_nano", int), Column("attributes", JSON))
        self.rounds = db.table(
            "rounds",
            Column("seq", int, primary=True, autoincrement=True), Column("work_id", str), Column("worklet_id", str, index=True),
            Column("round_id", str), Column("timestamp", str), Column("role", str), Column("text", str))

    def tx(self):
        return self.db.transaction()

    # ---- spans ----

    def insert_span(self, row: dict) -> None:
        self.db.insert(self.spans).values(**row).run()

    def get_span(self, span_id: str) -> dict | None:
        return self.db.select(self.spans).where(self.spans.c.span_id == span_id).one()

    def update_span(self, span_id: str, **changes) -> None:
        self.db.update(self.spans).where(self.spans.c.span_id == span_id).set(**changes).run()

    def _ordered(self, *conds) -> list[dict]:
        t = self.spans
        return self.db.select(t).where(*conds).order_by(t.c.start_time_unix_nano.asc(), t.c.span_id.asc()).all()

    def work_spans(self, work_id: str) -> list[dict]:
        """一个 work 的 work 段,一段一段按开始排(重新打开一次多一段)。"""
        return self._ordered(self.spans.c.work_id == work_id, self.spans.c.name == "work")

    def worklet_spans(self, worklet_id: str) -> list[dict]:
        return self._ordered(self.spans.c.worklet_id == worklet_id, self.spans.c.name == "worklet")

    def turn_spans(self, worklet_id: str) -> list[dict]:
        """一个工作单元的 agent 轮次(各段 first_round_id 不同,按它幂等写)。"""
        return self._ordered(self.spans.c.worklet_id == worklet_id, self.spans.c.name == "agent.turn")

    def open_spans(self, work_id: str, name: str) -> list[dict]:
        t = self.spans
        return self._ordered(t.c.work_id == work_id, t.c.name == name, t.c.end_time_unix_nano.is_null())

    def spans_of(self, work_ids: Sequence[str]) -> list[dict]:
        return self._ordered(self.spans.c.work_id.in_(work_ids))

    # ---- points ----

    def insert_point(self, row: dict) -> int:
        return self.db.insert(self.points).values(**row).run()

    def points_of(self, work_ids: Sequence[str]) -> list[dict]:
        t = self.points
        return self.db.select(t).where(t.c.work_id.in_(work_ids)).order_by(t.c.seq.asc()).all()

    # ---- 某人在轨迹里出现过的地方:开过段、关过段、打过点(按 user 走索引)----

    def touched_by(self, user: str) -> dict[str, int]:
        """work_id → 这个人在它上面最后一次出现的时间(Unix 纳秒)。"""
        out: dict[str, int] = {}

        def seen(work_id: str | None, t: int | None) -> None:
            if work_id and t is not None:
                out[work_id] = max(out.get(work_id, 0), t)

        s, p = self.spans, self.points
        for r in self.db.select(s).where(s.c.user_id == user).all():
            seen(r["work_id"], r["start_time_unix_nano"])
        for r in self.db.select(s).where(s.c.end_user_id == user).all():
            seen(r["work_id"], r["end_time_unix_nano"])
        for r in self.db.select(p).where(p.c.user_id == user).all():
            seen(r["work_id"], r["time_unix_nano"])
        return out

    # ---- rounds ----

    def read_rounds(self, worklet_id: str) -> list[dict]:
        t = self.rounds
        return self.db.select(t).where(t.c.worklet_id == worklet_id).order_by(t.c.seq.asc()).all()

    def insert_round(self, row: dict) -> None:
        self.db.insert(self.rounds).values(**row).run()


__all__ = ["WorkRepo", "TraceRepo"]
