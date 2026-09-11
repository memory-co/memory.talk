"""work 自己的 append-only 事件:开工 / 状态 / 会话 / 做完。"""
from __future__ import annotations

from memorytalk.backend.models.work import Event

from .repo import WorkRepo
from .tree import now


class Events:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def emit(self, work_id: str, type_: str, **data) -> Event:
        e = Event(ts=now(), type=type_, data=data)
        self.repo.append(work_id, "events", e.model_dump())
        return e

    def read(self, work_id: str) -> list[Event]:
        return [Event(**l) for l in self.repo.read(work_id, "events")]
