"""~/.memory.talk 的布局(store.md §1):memory/ 是 git 仓库,tasks/ 是裸文件。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryLayout:
    root: Path                      # memory/ 仓库根

    @property
    def cards(self) -> Path:
        return self.root / "cards"

    @property
    def issues(self) -> Path:
        return self.root / "issues"

    def card_path(self, card_id: str) -> Path:
        return self.cards / f"{card_id}.md"

    def issue_path(self, issue_id: str) -> Path:
        return self.issues / f"{issue_id}.json"

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()


@dataclass(frozen=True)
class TasksLayout:
    """tasks/<task_id>/ —— 每个 task 一个目录,裸文件(store.md §4)。"""
    root: Path

    def task_dir(self, task_id: str) -> Path:
        return self.root / task_id

    def task_json(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "task.json"

    def canvas_json(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "canvas.json"

    def members_json(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "members.json"

    def events_jsonl(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "events.jsonl"

    def rounds_jsonl(self, task_id: str, member_id: str) -> Path:
        return self.task_dir(task_id) / "sessions" / member_id / "rounds.jsonl"
