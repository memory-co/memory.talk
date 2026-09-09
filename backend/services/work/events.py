"""work 自己的 append-only 事件:开工 / 状态 / 会话 / 做完。v3 events.jsonl 在 v5 唯一保留的地方。"""
from __future__ import annotations

from models.work import Event
from services.store import WorksLayout, append_line, read_lines

from .tree import now


class Events:
    def __init__(self, layout: WorksLayout) -> None:
        self.layout = layout

    def emit(self, work_id: str, type_: str, **data) -> Event:
        e = Event(ts=now(), type=type_, data=data)
        append_line(self.layout.events_jsonl(work_id), e.model_dump_json())
        return e

    def read(self, work_id: str) -> list[Event]:
        return [Event.model_validate_json(l) for l in read_lines(self.layout.events_jsonl(work_id))]
