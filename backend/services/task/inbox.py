"""收件箱:变动打过来的地方(manager.md §4)。append-only,不进 git。"""
from __future__ import annotations

from models.collect import InboxItem
from services.store import TasksLayout, append_line, read_lines


class Inbox:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    def path(self, task_id: str):
        return self.layout.task_dir(task_id) / "inbox.jsonl"

    def read(self, task_id: str) -> list[InboxItem]:
        return [InboxItem.model_validate_json(l) for l in read_lines(self.path(task_id))]

    def put(self, task_id: str, item: InboxItem) -> None:
        append_line(self.path(task_id), item.model_dump_json())
