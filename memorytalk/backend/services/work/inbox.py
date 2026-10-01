"""收件箱:变动打过来的地方(manager.md §4)。works.db 的 inbox 表,只追加;work_id 为空 = 没人管。
WorkService 和 MetasService 各包一个,但底下是同一个仓储(同一个 provider 实例)。"""
from __future__ import annotations

from memorytalk.backend.models.metas import InboxItem

from .repo import WorkRepo


class Inbox:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def read(self, work_id: str) -> list[InboxItem]:
        return [InboxItem(**r) for r in self.repo.read_inbox(work_id)]

    def put(self, work_id: str, item: InboxItem) -> None:
        self.repo.put_inbox(work_id, item.model_dump())

    def put_unmanaged(self, item: InboxItem) -> None:
        self.repo.put_inbox(None, item.model_dump())

    def unmanaged(self) -> list[InboxItem]:
        return [InboxItem(**r) for r in self.repo.read_unmanaged()]
