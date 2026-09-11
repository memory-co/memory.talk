"""收件箱:变动打过来的地方(manager.md §4)。append-only。"""
from __future__ import annotations

from memorytalk.backend.models.collections import InboxItem

from .repo import WorkRepo


class Inbox:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def read(self, work_id: str) -> list[InboxItem]:
        return [InboxItem(**l) for l in self.repo.read(work_id, "inbox")]

    def put(self, work_id: str, item: InboxItem) -> None:
        self.repo.append(work_id, "inbox", item.model_dump())

    def put_unmanaged(self, item: InboxItem) -> None:
        self.repo.append_unmanaged(item.model_dump())
