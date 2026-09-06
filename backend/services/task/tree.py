"""task 树:节点、父子、状态、完成收拢(task.md §2)。每个 task 一个目录,task.json 原子写。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from models.task import Task, TaskCreate, TaskNode, TaskStatus, TaskUpdate
from services.store import TasksLayout, atomic_write, read_text


class TaskNotFound(LookupError):
    pass


class TaskConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id() -> str:
    return "task_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)


class TaskTree:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    # ---- 读 ----

    def get(self, task_id: str) -> Task:
        text = read_text(self.layout.task_json(task_id))
        if text is None:
            raise TaskNotFound(task_id)
        return Task.model_validate_json(text)

    def all(self) -> list[Task]:
        out = []
        if not self.layout.root.is_dir():
            return out
        for d in sorted(self.layout.root.iterdir()):
            text = read_text(d / "task.json")
            if text is not None:
                out.append(Task.model_validate_json(text))
        return out

    def children(self, task_id: str) -> list[Task]:
        return [t for t in self.all() if t.parent == task_id]

    def forest(self, root: str | None = None) -> list[TaskNode]:
        tasks = self.all()
        nodes = {t.id: TaskNode(**t.model_dump()) for t in tasks}
        roots = []
        for n in nodes.values():
            if n.parent and n.parent in nodes:
                nodes[n.parent].children.append(n)
            else:
                roots.append(n)
        if root is None:
            return roots
        if root not in nodes:
            raise TaskNotFound(root)
        return [nodes[root]]

    # ---- 写 ----

    def _save(self, task: Task) -> None:
        atomic_write(self.layout.task_json(task.id), task.model_dump_json(indent=2) + "\n")

    def create(self, req: TaskCreate) -> Task:
        if req.parent:
            self.get(req.parent)
        task = Task(id=_new_id(), goal=req.goal, parent=req.parent, created_at=now())
        self._save(task)
        return task

    def update(self, task_id: str, req: TaskUpdate) -> Task:
        task = self.get(task_id)
        data = task.model_dump()
        if req.goal is not None:
            data["goal"] = req.goal
        if req.status is not None:
            data.update(self._transition(task, req.status))
        task = Task(**data)
        self._save(task)
        return task

    def _transition(self, task: Task, status: TaskStatus) -> dict:
        """完成 = 叶子做完,往上收拢:子 task 还没完的父 task 不能 done。"""
        if status == "done":
            pending = [c.id for c in self.children(task.id) if c.status not in ("done", "abandoned")]
            if pending:
                raise TaskConflict(f"{task.id} 还有未完成的子 task: {', '.join(pending)}")
            return {"status": status, "done_at": now()}
        if status == "abandoned":
            return {"status": status, "done_at": now()}
        return {"status": status, "done_at": None}
