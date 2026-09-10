"""WorkService:树、画布、会话(经 server 建现场)、痕迹、事件(docs/designs/v5/work.md)。"""
from __future__ import annotations

from datetime import datetime
from models.work import (Canvas, CanvasPut, Event, Members, Round, Session, SessionView, Work, WorkCreate,
                         WorkNode, WorkUpdate)
from services.servers import ServerService
from services.store import StoreService

from .canvas import CanvasStore
from .events import Events
from .inbox import Inbox
from .members import MemberRegistry
from .sessions import SessionNotFound, SessionRegistry
from .rounds import Rounds
from .tree import WorkConflict, WorkNotFound, WorkTree


class WorkService:
    def __init__(self, store: StoreService, servers: ServerService) -> None:
        self.servers = servers
        self.tree = WorkTree(store.works)
        self.canvas = CanvasStore(store.works)
        self.sessions = SessionRegistry(store.works)
        self.round_log = Rounds(store.works)
        self.events = Events(store.works)
        self.members = MemberRegistry(store.works)
        self.inbox = Inbox(store.works)
        self.layout = store.works

    # ---- 成员(人):谁在操作 / 操作过。只记,不拦 ----

    def touch(self, work_id: str, user: str | None) -> None:
        if user:
            self.tree.get(work_id)
            self.members.touch(work_id, user)

    def list_members(self, work_id: str) -> Members:
        self.tree.get(work_id)
        return self.members.list(work_id)

    # ---- 收件箱 / manager:work 自己的变动沿树打给管它的 work ----

    def read_inbox(self, work_id: str):
        self.tree.get(work_id)
        return self.inbox.read(work_id)

    def manager_of(self, work_id: str) -> str | None:
        """works/<id>/manager.json 里的 work;没有 → 父 work;根没有 → None。"""
        import json
        from services.store import read_text
        text = read_text(self.layout.manager_json(work_id))
        if text:
            try:
                t = json.loads(text).get("work")
                if t:
                    return t
            except json.JSONDecodeError:
                pass
        return self.tree.get(work_id).parent

    def set_manager(self, work_id: str, work: str | None) -> str | None:
        import json
        from services.store import atomic_write
        self.tree.get(work_id)
        p = self.layout.manager_json(work_id)
        if work:
            atomic_write(p, json.dumps({"work": work}) + "\n")
        elif p.exists():
            p.unlink()
        return self.manager_of(work_id)

    def _deliver(self, work_id: str, subject: str, by: str | None = None) -> None:
        from models.collections import InboxItem
        from .tree import now
        target = self.manager_of(work_id)
        if not target or target == work_id:
            return
        self.inbox.put(target, InboxItem(ts=now(), layer="work", path=work_id, subject=subject, by=by,
                                         routed_by=work_id if self.layout.manager_json(work_id).exists() else "parent"))

    # ---- 树 ----

    def create(self, req: WorkCreate) -> Work:
        work = self.tree.create(req)
        self.events.emit(work.id, "created", goal=work.goal, parent=work.parent)
        self._deliver(work.id, f"created: {work.goal[:60]}")
        return work

    def get(self, work_id: str) -> Work:
        return self.tree.get(work_id)

    def forest(self, root: str | None = None) -> list[WorkNode]:
        return self.tree.forest(root)

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
        """做完:会话冻结——现场销毁,登记留着(可回去看痕迹,不再是干活的地方)。"""
        for m in self.sessions.list(work_id):
            try:
                self.servers.destroy(m.server, m.id)
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

    # ---- 会话:在 work 里打开,就是它的 ----

    def attach(self, work_id: str, raw_uri: str) -> SessionView:
        work = self.tree.get(work_id)
        if work.status in ("done", "abandoned"):
            raise WorkConflict(f"{work_id} 已结束,不再是干活的地方")
        uri, server = self.servers.resolve(raw_uri)
        m = self.sessions.add(work_id, raw_uri, uri.scheme, server.name, None)
        try:
            live, _ = self.servers.open(m.id, raw_uri, since_mtime=_epoch(m.created_at))
        except Exception:
            self.sessions.remove(work_id, m.id)      # 现场没建起来,登记不能留
            raise
        if live.cwd:
            m = self._set_cwd(work_id, m, live.cwd)
        self.events.emit(work_id, "session.attached", session=m.id, uri=raw_uri, server=server.name)
        return SessionView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def reattach(self, work_id: str, session_id: str) -> SessionView:
        """重入:同一会话再次打开,幂等地取回同一个现场。"""
        m = self.sessions.get(work_id, session_id)
        live, _ = self.servers.open(m.id, m.uri, since_mtime=_epoch(m.created_at))
        m = self.sessions.touch(work_id, session_id)
        return SessionView(**m.model_dump(), alive=True, window=live.window, handle=live.handle)

    def _set_cwd(self, work_id: str, m: Session, cwd: str) -> Session:
        sessions = self.sessions._load(work_id)
        for i, x in enumerate(sessions):
            if x.id == m.id:
                sessions[i] = x.model_copy(update={"cwd": cwd})
                self.sessions._save(work_id, sessions)
                return sessions[i]
        return m

    def list_sessions(self, work_id: str) -> list[SessionView]:
        self.tree.get(work_id)
        out = []
        for m in self.sessions.list(work_id):
            alive = self.servers.alive(m.server, m.id)
            out.append(SessionView(**m.model_dump(), alive=alive))
        return out

    def detach(self, work_id: str, session_id: str) -> None:
        """关闭即回收:销毁现场 + 删登记。"""
        m = self.sessions.get(work_id, session_id)
        self.servers.destroy(m.server, m.id)
        self.sessions.remove(work_id, session_id)
        self.events.emit(work_id, "session.detached", session=session_id)

    # ---- 痕迹 ----

    def capture(self, work_id: str, session_id: str, lines: int = 200) -> str:
        m = self.sessions.get(work_id, session_id)
        h = self._handle(m)
        if not hasattr(h, "capture"):
            raise WorkConflict(f"{session_id} 的把手没有 capture")
        return h.capture(lines)

    def rounds(self, work_id: str, session_id: str) -> list[Round]:
        m = self.sessions.get(work_id, session_id)
        work = self.tree.get(work_id)
        if work.status not in ("done", "abandoned"):
            h = self._handle(m)
            if hasattr(h, "rounds"):
                self.round_log.sync(work_id, session_id, h.rounds())
        return self.round_log.read(work_id, session_id)

    def _handle(self, m: Session):
        return self.servers.handle(m.server, m.id, m.uri, m.cwd, _epoch(m.created_at))

    def history(self, work_id: str) -> list[Event]:
        self.tree.get(work_id)
        return self.events.read(work_id)


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


__all__ = ["WorkService", "WorkNotFound", "WorkConflict", "SessionNotFound"]
