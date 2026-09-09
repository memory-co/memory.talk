"""work 树:节点、父子、状态、完成收拢(work.md §2)。每个 work 一个目录,work.json 原子写。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from models.work import Work, WorkCreate, WorkNode, WorkStatus, WorkUpdate
from services.store import WorksLayout, atomic_write, read_text


class WorkNotFound(LookupError):
    pass


class WorkConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id() -> str:
    return "work_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)


class WorkTree:
    def __init__(self, layout: WorksLayout) -> None:
        self.layout = layout

    # ---- 读 ----

    def get(self, work_id: str) -> Work:
        text = read_text(self.layout.work_json(work_id))
        if text is None:
            raise WorkNotFound(work_id)
        return Work.model_validate_json(text)

    def all(self) -> list[Work]:
        out = []
        if not self.layout.root.is_dir():
            return out
        for d in sorted(self.layout.root.iterdir()):
            text = read_text(d / "work.json")
            if text is not None:
                out.append(Work.model_validate_json(text))
        return out

    def children(self, work_id: str) -> list[Work]:
        return [t for t in self.all() if t.parent == work_id]

    def forest(self, root: str | None = None) -> list[WorkNode]:
        works = self.all()
        nodes = {t.id: WorkNode(**t.model_dump()) for t in works}
        roots = []
        for n in nodes.values():
            if n.parent and n.parent in nodes:
                nodes[n.parent].children.append(n)
            else:
                roots.append(n)
        if root is None:
            return roots
        if root not in nodes:
            raise WorkNotFound(root)
        return [nodes[root]]

    # ---- 写 ----

    def _save(self, work: Work) -> None:
        atomic_write(self.layout.work_json(work.id), work.model_dump_json(indent=2) + "\n")

    def create(self, req: WorkCreate) -> Work:
        if req.parent:
            self.get(req.parent)
        work = Work(id=_new_id(), goal=req.goal, parent=req.parent, created_at=now())
        self._save(work)
        return work

    def update(self, work_id: str, req: WorkUpdate) -> Work:
        work = self.get(work_id)
        data = work.model_dump()
        if req.goal is not None:
            data["goal"] = req.goal
        if req.status is not None:
            data.update(self._transition(work, req.status))
        work = Work(**data)
        self._save(work)
        return work

    def _transition(self, work: Work, status: WorkStatus) -> dict:
        """完成 = 叶子做完,往上收拢:子 work 还没完的父 work 不能 done。"""
        if status == "done":
            pending = [c.id for c in self.children(work.id) if c.status not in ("done", "abandoned")]
            if pending:
                raise WorkConflict(f"{work.id} 还有未完成的子 work: {', '.join(pending)}")
            return {"status": status, "done_at": now()}
        if status == "abandoned":
            return {"status": status, "done_at": now()}
        return {"status": status, "done_at": None}
