"""task 自己的 append-only 事件:开工 / 状态 / 会话 / 做完。v3 events.jsonl 在 v5 唯一保留的地方。"""
from __future__ import annotations

from models.task import Event
from services.store import TasksLayout, append_line, read_lines

from .tree import now


class Events:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    def emit(self, task_id: str, type_: str, **data) -> Event:
        e = Event(ts=now(), type=type_, data=data)
        append_line(self.layout.events_jsonl(task_id), e.model_dump_json())
        return e

    def read(self, task_id: str) -> list[Event]:
        return [Event.model_validate_json(l) for l in read_lines(self.layout.events_jsonl(task_id))]
