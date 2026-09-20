"""WorkService:树、画布、工作单元(经 server 建现场)、痕迹、事件(docs/designs/v5/work.md)。"""
from __future__ import annotations

from memorytalk.backend.models.search import SearchHit

from datetime import datetime
from memorytalk.backend.models.work import (Canvas, CanvasPut, Event, Round, Worklet, WorkletView, Work, WorkCreate, WorkUsers,
                         WorkNode, WorkUpdate)
from memorytalk.backend.services.work_servers import WorkServerService
from memorytalk.backend.services.store import StoreService

from .repo import WorkRepo

from .canvas import CanvasStore
from .events import Events
from .inbox import Inbox
from .users import WorkUserRegistry
from .worklets import WorkletNotFound, WorkletRegistry
from .rounds import Rounds
from .tree import WorkConflict, WorkNotFound, WorkTree


class WorkService:
    def __init__(self, store: StoreService, servers: WorkServerService) -> None:
        self.work_servers = servers
        self.repo: WorkRepo = store.work_repo
        self.tree = WorkTree(self.repo)
        self.canvas = CanvasStore(self.repo)
        self.worklets = WorkletRegistry(self.repo)
        self.round_log = Rounds(self.repo)
        self.events = Events(self.repo)
        self.users = WorkUserRegistry(self.repo)
        self.inbox = Inbox(self.repo)

    # ---- user:谁在操作 / 操作过。只记,不拦 ----

    def touch(self, work_id: str, user: str | None) -> None:
        if user:
            self.tree.get(work_id)
            self.users.touch(work_id, user)

    def list_users(self, work_id: str) -> WorkUsers:
        self.tree.get(work_id)
        return self.users.list(work_id)

    # ---- 收件箱 / manager:work 自己的变动沿树打给管它的 work ----

    def read_inbox(self, work_id: str):
        self.tree.get(work_id)
        return self.inbox.read(work_id)

    def manager_of(self, work_id: str) -> str | None:
        """works/<id>/manager.json 里的 work;没有 → 父 work;根没有 → None。"""
        doc = self.repo.get_doc(work_id, "manager")
        if doc and doc.get("work"):
            return doc["work"]
        return self.tree.get(work_id).parent

    def set_manager(self, work_id: str, work: str | None) -> str | None:
        self.tree.get(work_id)
        if work:
            self.repo.put_doc(work_id, "manager", {"work": work})
        else:
            self.repo.del_doc(work_id, "manager")
        return self.manager_of(work_id)

    def _deliver(self, work_id: str, subject: str, by: str | None = None) -> None:
        from memorytalk.backend.models.metas import InboxItem
        from .tree import now
        target = self.manager_of(work_id)
        if not target or target == work_id:
            return
        explicit = bool(self.repo.get_doc(work_id, "manager"))
        self.inbox.put(target, InboxItem(ts=now(), layer="work", path=work_id, subject=subject, by=by,
                                         routed_by=work_id if explicit else "parent"))

    # ---- 树 ----

    def create(self, req: WorkCreate, created_by: str | None = None) -> Work:
        work = self.tree.create(req, created_by)
        self.events.emit(work.id, "created", goal=work.goal, parent=work.parent, by=created_by)
        self._deliver(work.id, f"created: {work.goal[:60]}", by=created_by)
        if created_by:
            self.users.touch(work.id, created_by)      # 建它的人自动是 users 里的第一个
        return work

    def get(self, work_id: str) -> Work:
        return self.tree.get(work_id)

    def search(self, q: str, limit: int = 20) -> list[SearchHit]:
        """目标里含 q 的 work,新的在前。"""
        needle = q.lower()
        found = [w for w in self.tree.all() if needle in w.goal.lower()]
        found.sort(key=lambda w: w.created_at, reverse=True)
        return [SearchHit(kind="work", id=w.id, title=w.goal, snippet=w.status, status=w.status) for w in found[:limit]]

    def forest(self, root: str | None = None, created_by: str | None = None) -> list[WorkNode]:
        return self.tree.forest(root, created_by)

    def update(self, work_id: str, req: WorkUpdate) -> Work:
        before = self.tree.get(work_id)
        work = self.tree.update(work_id, req)
        if req.status and req.status != before.status:
            self.events.emit(work_id, "status", **{"from": before.status, "to": work.status})
            self._deliver(work_id, f"status {before.status} -> {work.status}")
        if work.status in ("done", "abandoned") and before.status not in ("done", "abandoned"):
            self._freeze(work_id)
        return work

    def _freeze(self, work_id: str) -> None:
        """做完:工作单元冻结——现场销毁,登记留着(可回去看痕迹,不再是干活的地方)。"""
        for m in self.worklets.list(work_id):
            try:
                self.work_servers.destroy(m.server, m.id)
            except Exception:
                pass
        self.events.emit(work_id, "frozen")

    # ---- 画布 ----

    def get_canvas(self, work_id: str) -> Canvas:
        self.tree.get(work_id)
        return self.canvas.get(work_id)

    def put_canvas(self, work_id: str, req: CanvasPut) -> Canvas:
        self.tree.get(work_id)
        return self.canvas.put(work_id, req)

    # ---- 工作单元:在 work 里打开,就是它的 ----

    def attach(self, work_id: str, raw_uri: str) -> WorkletView:
        work = self.tree.get(work_id)
        if work.status in ("done", "abandoned"):
            raise WorkConflict(f"{work_id} 已结束,不再是干活的地方")
        uri, server = self.work_servers.resolve(raw_uri)
        m = self.worklets.add(work_id, raw_uri, uri.scheme, server.name, None)
        try:
            live, _ = self.work_servers.open(m.id, raw_uri, since_mtime=_epoch(m.created_at))
        except Exception:
            self.worklets.remove(work_id, m.id)      # 现场没建起来,登记不能留
            raise
        if live.cwd:
            m = self._set_cwd(work_id, m, live.cwd)
        self.canvas.place(work_id, m.id)                                # 视图跟着记:进第一列末尾
        self.events.emit(work_id, "worklet.attached", worklet=m.id, uri=raw_uri, server=server.name)
        return WorkletView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def reattach(self, work_id: str, worklet_id: str) -> WorkletView:
        """重入:同一工作单元再次打开,幂等地取回同一个现场。"""
        m = self.worklets.get(work_id, worklet_id)
        live, _ = self.work_servers.open(m.id, m.uri, since_mtime=_epoch(m.created_at))
        m = self.worklets.touch(work_id, worklet_id)
        return WorkletView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def _set_cwd(self, work_id: str, m: Worklet, cwd: str) -> Worklet:
        return self.worklets.replace(work_id, m.model_copy(update={"cwd": cwd}))

    def list_worklets(self, work_id: str) -> list[WorkletView]:
        self.tree.get(work_id)
        out = []
        for m in self.worklets.list(work_id):
            alive = self.work_servers.alive(m.server, m.id)
            window = self.work_servers.window(m.server, m.id, m.uri) if alive else None      # 清单里就带窗,前端不用再 attach 一次
            out.append(WorkletView(**m.model_dump(), alive=alive, window=window, handle=self._handle(m).info() if alive else None))
        return out

    def detach(self, work_id: str, worklet_id: str) -> None:
        """关闭即回收:销毁现场 + 删登记。"""
        m = self.worklets.get(work_id, worklet_id)
        self.work_servers.destroy(m.server, m.id)
        self.worklets.remove(work_id, worklet_id)
        self.canvas.remove(work_id, worklet_id)
        self.events.emit(work_id, "worklet.detached", worklet=worklet_id)

    # ---- 痕迹 ----

    def rounds(self, work_id: str, worklet_id: str) -> list[Round]:
        m = self.worklets.get(work_id, worklet_id)
        work = self.tree.get(work_id)
        if work.status not in ("done", "abandoned"):
            h = self._handle(m)
            if hasattr(h, "rounds"):
                self.round_log.sync(work_id, worklet_id, h.rounds())
        return self.round_log.read(work_id, worklet_id)

    def _handle(self, m: Worklet):
        return self.work_servers.handle(m.server, m.id, m.uri, m.cwd, _epoch(m.created_at))

    def history(self, work_id: str) -> list[Event]:
        self.tree.get(work_id)
        return self.events.read(work_id)


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


__all__ = ["WorkService", "WorkNotFound", "WorkConflict", "WorkletNotFound", "WorkRepo"]
