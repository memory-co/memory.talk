"""manager 绑定 + 派活(issue.md §3、§4)。task 层未实现,这里只记 id。"""
from __future__ import annotations

from models.issue import Issue, Position


def bind_manager(issue: Issue, task_id: str | None) -> None:
    issue.manager_task = task_id


def spawn_task(position: Position, task_id: str) -> bool:
    if task_id in position.spawned_tasks:
        return False
    position.spawned_tasks.append(task_id)
    return True
