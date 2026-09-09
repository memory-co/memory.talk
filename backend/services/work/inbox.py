"""收件箱:变动打过来的地方(manager.md §4)。append-only,不进 git。"""
from __future__ import annotations

from models.collect import InboxItem
from services.store import WorksLayout, append_line, read_lines


class Inbox:
    def __init__(self, layout: WorksLayout) -> None:
        self.layout = layout

    def path(self, work_id: str):
        return self.layout.work_dir(work_id) / "inbox.jsonl"

    def read(self, work_id: str) -> list[InboxItem]:
        return [InboxItem.model_validate_json(l) for l in read_lines(self.path(work_id))]

    def put(self, work_id: str, item: InboxItem) -> None:
        append_line(self.path(work_id), item.model_dump_json())
