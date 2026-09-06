"""agent 会话的 rounds.jsonl:append-only;从把手拉新 round 追加进来。"""
from __future__ import annotations

from models.task import Round
from services.store import TasksLayout, append_line, read_lines


class Rounds:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    def read(self, task_id: str, session_id: str) -> list[Round]:
        return [Round.model_validate_json(l) for l in read_lines(self.layout.rounds_jsonl(task_id, session_id))]

    def sync(self, task_id: str, session_id: str, fresh: list[Round]) -> int:
        """把把手读到的 round 里还没记的追加进来,返回新增条数。"""
        path = self.layout.rounds_jsonl(task_id, session_id)
        seen = {r.id for r in self.read(task_id, session_id)}
        added = 0
        for r in fresh:
            if r.id in seen:
                continue
            append_line(path, r.model_dump_json())
            seen.add(r.id)
            added += 1
        return added
