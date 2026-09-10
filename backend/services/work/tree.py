"""work 树:节点、父子、状态、完成收拢(work.md §2)。IO 走仓储。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from models.work import Work, WorkCreate, WorkNode, WorkStatus, WorkUpdate

from .repo import WorkRepo


class WorkNotFound(LookupError):
    pass


class WorkConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id() -> str:
    return "work_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)


class WorkTree:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def get(self, work_id: str) -> Work:
        data = self.repo.get_work(work_id)
        if data is None:
            raise WorkNotFound(work_id)
        return Work(**data)

    def all(self, created_by: str | None = None) -> list[Work]:
        return [Work(**w) for w in self.repo.list_works(created_by=created_by)]

    def children(self, work_id: str) -> list[Work]:
        return [Work(**w) for w in self.repo.list_works(parent=work_id)]

    def forest(self, root: str | None = None, created_by: str | None = None) -> list[WorkNode]:
        works = self.all(created_by)
        nodes = {w.id: WorkNode(**w.model_dump()) for w in works}
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

    def _save(self, work: Work) -> None:
        self.repo.put_work(work.id, work.model_dump())

    def create(self, req: WorkCreate, created_by: str | None = None) -> Work:
        if req.parent:
            self.get(req.parent)
        work = Work(id=_new_id(), goal=req.goal, created_by=created_by, parent=req.parent, created_at=now())
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
