"""work 树:节点、父子、状态(运行中 / 归档)、manager(work.md §2)。树就是 works.parent 列;IO 走仓储。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from memorytalk.backend.models.work import Work, WorkCreate, WorkNode, WorkStatus, WorkUpdate

from .repo import WorkRepo


class WorkNotFound(LookupError):
    pass


class WorkConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id() -> str:
    return "work_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)


def _work(row: dict) -> Work:
    """works 的一行 → Work;manager / 计数器这些列不对外。"""
    return Work(**{k: row[k] for k in Work.model_fields if k != "viewers"}, viewers=row["viewers"] or [])


class WorkTree:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def get(self, work_id: str) -> Work:
        row = self.repo.get_work(work_id)
        if row is None:
            raise WorkNotFound(work_id)
        return _work(row)

    def all(self, created_by: str | None = None) -> list[Work]:
        return [_work(r) for r in self.repo.list_works(created_by=created_by)]

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

    def root_of(self, work_id: str) -> str:
        """沿 parent 走到根(trace id 由根算)。"""
        seen = set()
        while work_id not in seen:
            seen.add(work_id)
            row = self.repo.get_work(work_id)
            if row is None or not row["parent"]:
                return work_id
            work_id = row["parent"]
        return work_id

    def subtree(self, work_id: str) -> list[str]:
        """自己 + 所有子孙的 id(先序)。"""
        out, seen, stack = [], set(), [work_id]
        while stack:
            w = stack.pop()
            if w in seen:
                continue
            seen.add(w)
            out.append(w)
            stack.extend(reversed([r["id"] for r in self.repo.children(w)]))
        return out

    def create(self, req: WorkCreate, created_by: str | None = None) -> Work:
        """建节点(连同第一列);调用方包在事务里,好和投递一起提交。"""
        with self.repo.tx():
            if req.parent:
                self.get(req.parent)
            work = Work(id=_new_id(), goal=req.goal, created_by=created_by, parent=req.parent, created_at=now())
            self.repo.insert_work(work.model_dump(exclude={"viewers"}))
            return work

    def update(self, work_id: str, req: WorkUpdate) -> tuple[Work, Work]:
        """只改目标 / 状态这几列;交回(改前, 改后)。"""
        with self.repo.tx():
            before = self.get(work_id)
            changes: dict = {}
            if req.goal is not None:
                changes["goal"] = req.goal
            if req.status is not None:
                changes.update(self._transition(before, req.status))
            if changes:
                self.repo.update_work(work_id, **changes)
            return before, self.get(work_id)

    def _transition(self, work: Work, status: WorkStatus) -> dict:
        """只有两档:运行中 / 归档。归档记下时间,拿回运行中就清掉;不看子 work(各归各的)。"""
        if status == "archived":
            return {"status": status, "archived_at": work.archived_at if work.status == "archived" else now()}
        return {"status": status, "archived_at": None}

    # ---- manager:这棵子树的变动打给谁(空 = 父 work)----

    def route(self, work_id: str) -> tuple[str | None, bool]:
        """这个 work 的变动打给谁:(目标, 是不是显式设的)。没设 manager → 父 work;根没有 → None。"""
        row = self.repo.get_work(work_id)
        if row is None:
            raise WorkNotFound(work_id)
        return (row["manager"], True) if row["manager"] else (row["parent"], False)

    def set_manager(self, work_id: str, work: str | None) -> None:
        with self.repo.tx():
            self.get(work_id)
            self.repo.update_work(work_id, manager=work or None)
