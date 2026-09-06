"""TaskService:树、画布、会话(经 server 建现场)、痕迹、事件(docs/works/v5/task.md)。"""
from __future__ import annotations

from datetime import datetime
from models.task import (Canvas, CanvasPut, Event, Members, Round, Session, SessionView, Task, TaskCreate,
                         TaskNode, TaskUpdate)
from services.servers import ServerService
from services.store import StoreService

from .canvas import CanvasStore
from .events import Events
from .members import MemberRegistry
from .sessions import SessionNotFound, SessionRegistry
from .rounds import Rounds
from .tree import TaskConflict, TaskNotFound, TaskTree


class TaskService:
    def __init__(self, store: StoreService, servers: ServerService) -> None:
        self.servers = servers
        self.tree = TaskTree(store.tasks)
        self.canvas = CanvasStore(store.tasks)
        self.sessions = SessionRegistry(store.tasks)
        self.round_log = Rounds(store.tasks)
        self.events = Events(store.tasks)
        self.members = MemberRegistry(store.tasks)

    # ---- 成员(人):谁在操作 / 操作过。只记,不拦 ----

    def touch(self, task_id: str, user: str | None) -> None:
        if user:
            self.tree.get(task_id)
            self.members.touch(task_id, user)

    def list_members(self, task_id: str) -> Members:
        self.tree.get(task_id)
        return self.members.list(task_id)

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
        """做完:会话冻结——现场销毁,登记留着(可回去看痕迹,不再是干活的地方)。"""
        for m in self.sessions.list(task_id):
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

    # ---- 会话:在 task 里打开,就是它的 ----

    def attach(self, task_id: str, raw_uri: str) -> SessionView:
        task = self.tree.get(task_id)
        if task.status in ("done", "abandoned"):
            raise TaskConflict(f"{task_id} 已结束,不再是干活的地方")
        uri, server = self.servers.resolve(raw_uri)
        m = self.sessions.add(task_id, raw_uri, uri.scheme, server.name, None)
        try:
            live, _ = self.servers.open(m.id, raw_uri, since_mtime=_epoch(m.created_at))
        except Exception:
            self.sessions.remove(task_id, m.id)      # 现场没建起来,登记不能留
            raise
        if live.cwd:
            m = self._set_cwd(task_id, m, live.cwd)
        self.events.emit(task_id, "session.attached", session=m.id, uri=raw_uri, server=server.name)
        return SessionView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def reattach(self, task_id: str, session_id: str) -> SessionView:
        """重入:同一会话再次打开,幂等地取回同一个现场。"""
        m = self.sessions.get(task_id, session_id)
        live, _ = self.servers.open(m.id, m.uri, since_mtime=_epoch(m.created_at))
        m = self.sessions.touch(task_id, session_id)
        return SessionView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def _set_cwd(self, task_id: str, m: Session, cwd: str) -> Session:
        sessions = self.sessions._load(task_id)
        for i, x in enumerate(sessions):
            if x.id == m.id:
                sessions[i] = x.model_copy(update={"cwd": cwd})
                self.sessions._save(task_id, sessions)
                return sessions[i]
        return m

    def list_sessions(self, task_id: str) -> list[SessionView]:
        self.tree.get(task_id)
        out = []
        for m in self.sessions.list(task_id):
            alive = self.servers.alive(m.server, m.id)
            out.append(SessionView(**m.model_dump(), alive=alive))
        return out

    def detach(self, task_id: str, session_id: str) -> None:
        """关闭即回收:销毁现场 + 删登记。"""
        m = self.sessions.get(task_id, session_id)
        self.servers.destroy(m.server, m.id)
        self.sessions.remove(task_id, session_id)
        self.events.emit(task_id, "session.detached", session=session_id)

    # ---- 痕迹 ----

    def capture(self, task_id: str, session_id: str, lines: int = 200) -> str:
        m = self.sessions.get(task_id, session_id)
        h = self._handle(m)
        if not hasattr(h, "capture"):
            raise TaskConflict(f"{session_id} 的把手没有 capture")
        return h.capture(lines)

    def rounds(self, task_id: str, session_id: str) -> list[Round]:
        m = self.sessions.get(task_id, session_id)
        task = self.tree.get(task_id)
        if task.status not in ("done", "abandoned"):
            h = self._handle(m)
            if hasattr(h, "rounds"):
                self.round_log.sync(task_id, session_id, h.rounds())
        return self.round_log.read(task_id, session_id)

    def _handle(self, m: Session):
        return self.servers.handle(m.server, m.id, m.uri, m.cwd, _epoch(m.created_at))

    def history(self, task_id: str) -> list[Event]:
        self.tree.get(task_id)
        return self.events.read(task_id)


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


__all__ = ["TaskService", "TaskNotFound", "TaskConflict", "SessionNotFound"]
