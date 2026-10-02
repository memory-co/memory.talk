"""WorkService:树、列、工作单元(经 server 建现场)、痕迹、轨迹、谁在看(docs/designs/v5/work.md、work-store.md、work-trace.md)。

一个动作的写法固定:先在 works.db 一个事务里把读-改-写做完;建 / 销毁现场不在事务里;最后写 worktrace.db。
两个库之间没有原子提交——轨迹写失败只记日志,不让动作失败,也不回滚 work(轨迹丢了不伤 work)。"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from typing import Callable

from memorytalk.backend.models.metas import InboxItem
from memorytalk.backend.models.search import SearchHit
from memorytalk.backend.models.work import (Column, ColumnCreate, ColumnUpdate, Round, Worklet, WorkletMove,
                                            WorkletUpdate, WorkletView, Work, WorkCreate, WorkTrace, WorkUsers, WorkNode,
                                            WorkUpdate)
from memorytalk.backend.services.work_servers import WorkServerService
from memorytalk.backend.services.store import StoreService

from .columns import ColumnNotFound, Columns
from .inbox import Inbox
from .repo import TraceRepo, WorkRepo
from .rounds import Rounds
from .trace import STATUS_UNSET, Trace
from .tree import WorkConflict, WorkNotFound, WorkTree, now
from .viewers import Viewers
from .worklets import WorkletNotFound, WorkletRegistry

log = logging.getLogger(__name__)


class WorkService:
    def __init__(self, store: StoreService, servers: WorkServerService) -> None:
        self.work_servers = servers
        self.repo: WorkRepo = store.work_repo
        self.trace_repo: TraceRepo = store.trace_repo
        self.tree = WorkTree(self.repo)
        self.columns = Columns(self.repo)
        self.worklets = WorkletRegistry(self.repo)
        self.inbox = Inbox(self.repo)
        self.viewers = Viewers(self.repo)                  # 一起来就把所有 work 的 viewers 清空
        self.trace = Trace(self.trace_repo, self.tree)
        self.round_log = Rounds(self.trace_repo)
        self._busy: Counter[str] = Counter()              # 手上正在关 / 归档 / 重入的工作单元(只在内存里)
        self._busy_lock = threading.Lock()
        self._lifecycles: dict[str, threading.RLock] = {}  # 每个 work 一把:归档 / 重新打开 / 打开 / 重入一个一个来
        self._lifecycles_lock = threading.Lock()

    def _record(self, fn: Callable, *args, **kw) -> None:
        """写轨迹:works.db 已经提交了,这里失败只记日志,轨迹少一条不伤 work。"""
        try:
            fn(*args, **kw)
        except Exception:
            log.exception("轨迹没写进去:%s", getattr(fn, "__name__", fn))

    @contextmanager
    def _lifecycle(self, work_id: str):
        """同一个 work 的生命周期动作排队:归档(收 round、销毁现场、结束段)整个做完之前,别人不能把它重新打开,
        也不能把新开的工作单元登记进来、开段;不然归档会去结束重新打开后的新一段,旧的那段永远开着。
        进程内的锁,不是 works.db 事务——销毁现场、写 worktrace.db 都在它里面,事务里照样不做这些。"""
        with self._lifecycles_lock:
            lock = self._lifecycles.setdefault(work_id, threading.RLock())
        with lock:
            yield

    @contextmanager
    def _handling(self, *worklet_ids: str):
        """关掉 / 归档 / 重入期间这几个工作单元的现场在变(销毁了还没删登记、还没结束段;刚开起来还没接上段):
        列清单不拿它们判「现场没了」,段由那个动作自己结束或接着用。"""
        with self._busy_lock:
            self._busy.update(worklet_ids)
        try:
            yield
        finally:
            with self._busy_lock:
                self._busy.subtract(worklet_ids)
                self._busy = +self._busy                   # 去掉数到 0 的

    # ---- 谁在看:心跳 / 离开。只做可见性,不拦 ----

    def touch(self, work_id: str, user: str | None) -> None:
        """心跳(打开 / 操作一个 work 都算);顺带是 work 不存在时的 404。"""
        if user:
            self.tree.get(work_id)
            self.viewers.touch(work_id, user)

    def leave(self, work_id: str, user: str | None) -> WorkUsers:
        self.tree.get(work_id)
        if user:
            self.viewers.leave(work_id, user)
        return self.list_users(work_id)

    def list_users(self, work_id: str) -> WorkUsers:
        self.viewers.sweep()
        return WorkUsers(current=self.tree.get(work_id).viewers)

    # ---- 收件箱 / manager:work 自己的变动沿树打给管它的 work ----

    def read_inbox(self, work_id: str):
        self.tree.get(work_id)
        return self.inbox.read(work_id)

    def manager_of(self, work_id: str) -> str | None:
        """works.manager;没设 → 父 work;根没有 → None。"""
        return self.tree.route(work_id)[0]

    def set_manager(self, work_id: str, work: str | None) -> str | None:
        self.tree.set_manager(work_id, work)
        return self.manager_of(work_id)

    def _deliver(self, work_id: str, subject: str, by: str | None = None) -> None:
        """写进管它的 work 的收件箱;调用方包在同一个事务里。自己不投给自己。"""
        target, explicit = self.tree.route(work_id)
        if not target or target == work_id:
            return
        self.inbox.put(target, InboxItem(ts=now(), layer="work", path=work_id, subject=subject, by=by,
                                         routed_by=work_id if explicit else "parent"))

    # ---- 树 ----

    def create(self, req: WorkCreate, created_by: str | None = None) -> Work:
        with self.repo.tx():
            work = self.tree.create(req, created_by)
            self._deliver(work.id, f"created: {work.goal[:60]}", by=created_by)
        if created_by:
            self.viewers.touch(work.id, created_by)       # 建它的人这会儿就在看
        self._record(self.trace.work_started, work, created_by)
        return self.tree.get(work.id)

    def get(self, work_id: str) -> Work:
        self.viewers.sweep()
        return self.tree.get(work_id)

    def search(self, q: str, limit: int = 20) -> list[SearchHit]:
        """目标里含 q 的 work,新的在前。"""
        needle = q.lower()
        found = [w for w in self.tree.all() if needle in w.goal.lower()]
        found.sort(key=lambda w: w.created_at, reverse=True)
        return [SearchHit(kind="work", id=w.id, title=w.goal, snippet=w.status, status=w.status) for w in found[:limit]]

    def forest(self, root: str | None = None, created_by: str | None = None) -> list[WorkNode]:
        return self.tree.forest(root, created_by)

    def update(self, work_id: str, req: WorkUpdate, by: str | None = None) -> Work:
        self.tree.get(work_id)                                         # 不存在的先 404,不给它建锁
        with self._lifecycle(work_id):                                 # 从改状态到收尾(冻结 / 开新段)一口气做完
            with self.repo.tx():
                before, work = self.tree.update(work_id, req)
                if work.status != before.status:
                    self._deliver(work_id, f"status {before.status} -> {work.status}", by=by)
            if before.status == "archived" and work.status == "running":
                self._record(self.trace.work_started, work, by, archived_at=_nanos(before.archived_at))   # 重新打开 = 新的一段,link 指向上一段
                self._record(self._resume_live, work_id, by)
            if work.goal != before.goal:
                self._record(self.trace.work_renamed, work_id, work.goal, before.goal, by)
            if work.status == "archived" and before.status != "archived":
                self._freeze(work_id, by)
        return work

    def _freeze(self, work_id: str, by: str | None = None) -> None:
        """归档:工作单元冻结——先把 round 收齐,再销毁现场;登记和摆在哪都留着(可回去看痕迹,不再是干活的地方)。
        轨迹:开着的工作单元段和 work 段一起结束(reason archived)。一个个销毁到结束段之前,列清单不把它们记成 gone。"""
        worklets = self.worklets.list(work_id)
        with self._handling(*(m.id for m in worklets)):
            for m in worklets:
                self._final_sync(work_id, m)
                try:
                    self.work_servers.destroy(m.server, m.id)
                except Exception:
                    pass
            columns = {m.id: self._column_of(work_id, m.id) for m in worklets}
            self._record(self.trace.work_archived, work_id, by, columns)

    def _column_of(self, work_id: str, worklet_id: str) -> Column | None:
        """段上带的列(它此刻在哪一列)。读不出来就不带——归档已经提交了,不能因为这个让段结束不上 / 开不出来。"""
        try:
            return self.columns.column_of(work_id, worklet_id)
        except Exception:
            log.exception("没读出工作单元在哪一列:%s", worklet_id)
            return None

    def _resume_live(self, work_id: str, by: str | None) -> None:
        """重新打开:现场还活着的工作单元(网页的一直活着,不会有人去重入)接着开新的一段——
        不然它摆在列里却没有开着的段,之后关它、挪它都挂不上。tmux 的现场归档时销毁了,等重入再开。"""
        for m in self.worklets.list(work_id):
            if self.work_servers.alive(m.server, m.id):
                self.trace.worklet_started(work_id, m, self._column_of(work_id, m.id), by, resume=True)

    # ---- 列:每个动作一个方法,动了哪一列就打一个点(work-trace.md §2);交回动完的列清单 ----

    def list_columns(self, work_id: str) -> list[Column]:
        """从左到右。"""
        self.tree.get(work_id)
        return self.columns.list(work_id)

    def add_column(self, work_id: str, req: ColumnCreate, by: str | None = None) -> list[Column]:
        self.tree.get(work_id)
        cols, col = self.columns.add(work_id, req.alias.strip(), req.beside, req.side)
        self._record(self.trace.column_changed, work_id, "column.added", col, by)
        return cols

    def update_column(self, work_id: str, column_id: str, req: ColumnUpdate, by: str | None = None) -> list[Column]:
        self.tree.get(work_id)
        alias = req.alias.strip() if req.alias is not None else None
        cols, before, after = self.columns.update(work_id, column_id, alias, req.collapsed)
        if after.alias != before.alias:                  # 收起 / 展开不记(work-events.md §2)
            self._record(self.trace.column_changed, work_id, "column.renamed", after, by, **{"memorytalk.from": before.alias})
        return cols

    def remove_column(self, work_id: str, column_id: str, by: str | None = None) -> list[Column]:
        self.tree.get(work_id)
        cols, col = self.columns.remove(work_id, column_id)
        self._record(self.trace.column_changed, work_id, "column.removed", col, by)
        return cols

    # ---- 工作单元摆在哪:挪(打 worklet.moved 点)/ 收起(不记);交回工作单元清单 ----

    def move_worklet(self, work_id: str, worklet_id: str, req: WorkletMove, by: str | None = None) -> list[WorkletView]:
        self.worklets.get(work_id, worklet_id)
        (src, i), (dst, j) = self.columns.move(work_id, worklet_id, req.column, req.index)
        if (src.id, i) != (dst.id, j):
            self._record(self.trace.worklet_moved, work_id, worklet_id, (src, i), (dst, j), by)
        return self.list_worklets(work_id)

    def update_worklet(self, work_id: str, worklet_id: str, req: WorkletUpdate) -> list[WorkletView]:
        self.worklets.get(work_id, worklet_id)
        self.columns.set_collapsed(work_id, worklet_id, req.collapsed)
        return self.list_worklets(work_id)

    # ---- 工作单元:在 work 里打开,就是它的 ----

    def attach(self, work_id: str, raw_uri: str, column: str | None = None, by: str | None = None) -> WorkletView:
        """验 → 取号 → 建现场 → 登记并放进一列(一个事务)→ 开 worklet 段(work-store.md §6)。"""
        work = self.tree.get(work_id)
        if work.status == "archived":
            raise WorkConflict(f"{work_id} 已归档,不再是干活的地方")
        if column:
            self.columns.check(work_id, column)                         # 列不在就别建现场
        uri, server = self.work_servers.resolve(raw_uri)
        n, m = self.worklets.reserve(work_id)                           # 现场拿工作单元 id 当名字,先取号;建不起来这个号也不还
        m = m.model_copy(update={"uri": raw_uri, "scheme": uri.scheme, "server": server.name})
        live, _ = self.work_servers.open(m.id, raw_uri, since_mtime=_epoch(m.created_at))   # 建不起来到此为止,什么都没写
        if live.cwd:
            m = m.model_copy(update={"cwd": live.cwd})
        with self._lifecycle(work_id):              # 登记到开段一口气:归档要么在登记之前(这里看到已归档),要么等段开好了一起结束
            try:
                with self.repo.tx():
                    if self.tree.get(work_id).status == "archived":       # 建现场的这会儿被归档了:不登记,现场收掉
                        raise WorkConflict(f"{work_id} 已归档,不再是干活的地方")
                    self.worklets.add(work_id, n, m)
                    col, pos = self.columns.place(work_id, m.id, column)   # 开的时候就定列:给了放那列末尾,没给放最左一列
            except Exception:
                self._destroy_quietly(m)                                 # 登记没写进去,现场不能留
                raise
            self._record(self.trace.worklet_started, work_id, m, col, by)
        return WorkletView(**m.model_dump(), column=col.id, position=pos, alive=True, window=live.window, handle=live.handle)

    def reattach(self, work_id: str, worklet_id: str, by: str | None = None) -> WorkletView:
        """重入:同一工作单元再次打开,幂等地取回同一个现场。段已经结束了(现场没了 / 归档后又重新打开)就接着开新的一段。
        已归档的 work 不能重入(409,和打开一样):不然归档的 work 里有活的现场、结束了的 work 段下面开着一段 worklet 段。"""
        m = self.worklets.get(work_id, worklet_id)
        with self._lifecycle(work_id), self._handling(m.id):       # 不夹在归档的半中间(销毁了、段还没结束)
            if self.tree.get(work_id).status == "archived":     # 在锁里看:等着归档做完的重入,醒来看到的就是已归档
                raise WorkConflict(f"{work_id} 已归档,不再是干活的地方")
            live, _ = self.work_servers.open(m.id, m.uri, since_mtime=_epoch(m.created_at))
            m = self.worklets.touch(work_id, worklet_id)
            self._record(self.trace.worklet_started, work_id, m, self._column_of(work_id, m.id), by, resume=True)
        return WorkletView(**m.model_dump(), **self.worklets.placement(work_id, m.id), alive=True, window=live.window, handle=live.handle)

    def list_worklets(self, work_id: str) -> list[WorkletView]:
        """清单(按开的先后,各自带摆在哪一列哪个位置);现场自己没了、段还开着的,顺手把段结束掉(reason gone)。"""
        self.tree.get(work_id)
        out, gone = [], []
        for m, at in self.worklets.placed(work_id):
            alive = self.work_servers.alive(m.server, m.id)
            window = self.work_servers.window(m.server, m.id, m.uri) if alive else None      # 清单里就带窗,前端不用再 attach 一次
            out.append(WorkletView(**m.model_dump(), **at, alive=alive, window=window, handle=self._handle(m).info() if alive else None))
            if not alive:
                gone.append(m)
        for m in gone:
            self._record(self._gone, work_id, m)
        return out

    def _gone(self, work_id: str, m: Worklet) -> None:
        """现场自己没了(命令跑完了、机器重启了):不算出错,status 保持 Unset。
        正在关 / 归档 / 重入的不算;结束之前再看一眼现场,刚被重入开起来的也不算。"""
        with self._busy_lock:
            if self._busy[m.id]:
                return
        if self.work_servers.alive(m.server, m.id):
            return
        if span := self.trace.open_worklet_span(m.id):
            self.trace.worklet_ended(span, "gone", None, self._column_of(work_id, m.id), status=STATUS_UNSET)

    def detach(self, work_id: str, worklet_id: str, by: str | None = None) -> None:
        """关闭即回收:收齐 round → 销毁现场 → 从列里拿掉并删登记(一个事务)→ 结束 worklet 段。"""
        m = self.worklets.get(work_id, worklet_id)
        with self._handling(m.id):
            if self.tree.get(work_id).status != "archived":   # 登记删了就再也拿不到把手了;归档的已经收过最后一次,冻住的不再追加
                self._final_sync(work_id, m)
            self.work_servers.destroy(m.server, m.id)
            with self.repo.tx():
                col = self.columns.unplace(work_id, worklet_id)
                self.worklets.remove(work_id, worklet_id)
            self._record(self._closed, work_id, m, col, by)

    def _closed(self, work_id: str, m: Worklet, col: Column | None, by: str | None) -> None:
        """结束开着的 worklet 段(detached);已经没有开着的段(现场没了 / 归档过、重新打开后没重入)就打一个点记下谁关的。"""
        span = self.trace.open_worklet_span(m.id)
        if not (span and self.trace.worklet_ended(span, "detached", by, col)):
            self.trace.worklet_closed(work_id, m.id, col, by)

    def _destroy_quietly(self, m: Worklet) -> None:
        try:
            self.work_servers.destroy(m.server, m.id)
        except Exception:
            log.exception("现场没收掉:%s", m.id)

    # ---- 痕迹 ----

    def rounds(self, work_id: str, worklet_id: str) -> list[Round]:
        m = self.worklets.get(work_id, worklet_id)
        if self.tree.get(work_id).status != "archived":
            self._sync(work_id, m)
        return self.round_log.read(worklet_id)

    def _sync(self, work_id: str, m: Worklet) -> None:
        """从把手拉新 round 追加进 worktrace.db;有新的就重切一遍 agent 轮次(轨迹,失败只记日志)。"""
        h = self._handle(m)
        if hasattr(h, "rounds") and self.round_log.sync(work_id, m.id, h.rounds()):
            self._record(self.trace.turns, work_id, m.id)

    def _final_sync(self, work_id: str, m: Worklet) -> None:
        """关掉 / 归档之前最后收一次 round:尽力而为,失败不挡动作。"""
        try:
            self._sync(work_id, m)
        except Exception:
            log.exception("最后一次收 round 失败:%s", m.id)

    def _handle(self, m: Worklet):
        return self.work_servers.handle(m.server, m.id, m.uri, m.cwd, _epoch(m.created_at))

    # ---- 轨迹 ----

    def trace_of(self, work_id: str, subtree: bool = False) -> WorkTrace:
        """这个 work(subtree = 连同所有子孙)的段和点,OTLP/JSON。"""
        self.tree.get(work_id)
        return WorkTrace(**self.trace.read(self.tree.subtree(work_id) if subtree else [work_id]))


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _nanos(iso: str | None) -> int | None:
    return int(_epoch(iso)) * 1_000_000_000 if iso else None


__all__ = ["WorkService", "WorkNotFound", "WorkConflict", "WorkletNotFound", "ColumnNotFound", "WorkRepo", "TraceRepo"]
