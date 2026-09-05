"""TaskService:树、画布、成员(经 server 建现场)、痕迹、事件(docs/works/v5/task.md)。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from models.task import (Canvas, CanvasPut, Event, Member, MemberView, Round, Task, TaskCreate,
                         TaskNode, TaskUpdate)
from services.servers import ServerService, parse_uri
from services.store import StoreService

from .canvas import CanvasStore
from .events import Events
from .members import MemberNotFound, MemberRegistry
from .sessions import Sessions
from .tree import TaskConflict, TaskNotFound, TaskTree


class TaskService:
    def __init__(self, store: StoreService, servers: ServerService) -> None:
        self.servers = servers
        self.tree = TaskTree(store.tasks)
        self.canvas = CanvasStore(store.tasks)
        self.members = MemberRegistry(store.tasks)
        self.sessions = Sessions(store.tasks)
        self.events = Events(store.tasks)

    # ---- 树 ----

    def create(self, req: TaskCreate) -> Task:
        task = self.tree.create(req)
        self.events.emit(task.id, "created", goal=task.goal, parent=task.parent)
        return task

    def get(self, task_id: str) -> Task:
        return self.tree.get(task_id)

    def forest(self, root: str | None = None) -> list[TaskNode]:
        return self.tree.forest(root)

    def update(self, task_id: str, req: TaskUpdate) -> Task:
        before = self.tree.get(task_id)
        task = self.tree.update(task_id, req)
        if req.status and req.status != before.status:
            self.events.emit(task_id, "status", **{"from": before.status, "to": task.status})
        if task.status in ("done", "abandoned") and before.status not in ("done", "abandoned"):
            self._freeze(task_id)
        return task

    def _freeze(self, task_id: str) -> None:
        """做完:成员冻结——现场销毁,登记留着(可回去看痕迹,不再是干活的地方)。"""
        for m in self.members.list(task_id):
            try:
                self.servers.destroy(m.server, m.id)
            except Exception:
                pass
        self.events.emit(task_id, "frozen")

    # ---- 画布 ----

    def get_canvas(self, task_id: str) -> Canvas:
        self.tree.get(task_id)
        return self.canvas.get(task_id)

    def put_canvas(self, task_id: str, req: CanvasPut) -> Canvas:
        self.tree.get(task_id)
        return self.canvas.put(task_id, req)

    # ---- 成员:在 task 里打开,就是它的 ----

    def attach(self, task_id: str, raw_uri: str) -> MemberView:
        task = self.tree.get(task_id)
        if task.status in ("done", "abandoned"):
            raise TaskConflict(f"{task_id} 已结束,不再是干活的地方")
        uri, server = self.servers.resolve(raw_uri)
        m = self.members.add(task_id, raw_uri, uri.scheme, server.name, None)
        live, _ = self.servers.open(m.id, raw_uri, since_mtime=_epoch(m.created_at))
        if live.cwd:
            m = self._set_cwd(task_id, m, live.cwd)
        self.events.emit(task_id, "member.attached", member=m.id, uri=raw_uri, server=server.name)
        return MemberView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def reattach(self, task_id: str, member_id: str) -> MemberView:
        """重入:同一成员再次打开,幂等地取回同一个现场。"""
        m = self.members.get(task_id, member_id)
        live, _ = self.servers.open(m.id, m.uri, since_mtime=_epoch(m.created_at))
        m = self.members.touch(task_id, member_id)
        return MemberView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def _set_cwd(self, task_id: str, m: Member, cwd: str) -> Member:
        members = self.members._load(task_id)
        for i, x in enumerate(members):
            if x.id == m.id:
                members[i] = x.model_copy(update={"cwd": cwd})
                self.members._save(task_id, members)
                return members[i]
        return m

    def list_members(self, task_id: str) -> list[MemberView]:
        self.tree.get(task_id)
        out = []
        for m in self.members.list(task_id):
            alive = self.servers.alive(m.server, m.id)
            out.append(MemberView(**m.model_dump(), alive=alive))
        return out

    def detach(self, task_id: str, member_id: str) -> None:
        """关闭即回收:销毁现场 + 删登记。"""
        m = self.members.get(task_id, member_id)
        self.servers.destroy(m.server, m.id)
        self.members.remove(task_id, member_id)
        self.events.emit(task_id, "member.detached", member=member_id)

    # ---- 痕迹 ----

    def capture(self, task_id: str, member_id: str, lines: int = 200) -> str:
        m = self.members.get(task_id, member_id)
        h = self._handle(m)
        if not hasattr(h, "capture"):
            raise TaskConflict(f"{member_id} 的把手没有 capture")
        return h.capture(lines)

    def rounds(self, task_id: str, member_id: str) -> list[Round]:
        m = self.members.get(task_id, member_id)
        task = self.tree.get(task_id)
        if task.status not in ("done", "abandoned"):
            h = self._handle(m)
            if hasattr(h, "rounds"):
                self.sessions.sync(task_id, member_id, h.rounds())
        return self.sessions.read(task_id, member_id)

    def _handle(self, m: Member):
        server = self.servers.registry.by_name(m.server)
        if m.server == "agent":
            return server.handle(m.id, parse_uri(m.uri), Path(m.cwd or "."), _epoch(m.created_at))
        if m.server == "terminal":
            return server.handle(m.id)
        raise TaskConflict(f"{m.server} server 没有把手")

    def history(self, task_id: str) -> list[Event]:
        self.tree.get(task_id)
        return self.events.read(task_id)


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


__all__ = ["TaskService", "TaskNotFound", "TaskConflict", "MemberNotFound"]
