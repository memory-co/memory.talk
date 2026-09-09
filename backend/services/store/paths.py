"""~/.memory.talk 的布局(store.md §1):memory/ 是 git 仓库,works/ 是裸文件。"""
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
class WorksLayout:
    """works/<work_id>/ —— 每个 work 一个目录,裸文件(store.md §4)。"""
    root: Path

    def work_dir(self, work_id: str) -> Path:
        return self.root / work_id

    def work_json(self, work_id: str) -> Path:
        return self.work_dir(work_id) / "work.json"

    def canvas_json(self, work_id: str) -> Path:
        return self.work_dir(work_id) / "canvas.json"

    def sessions_json(self, work_id: str) -> Path:
        return self.work_dir(work_id) / "sessions.json"

    def events_jsonl(self, work_id: str) -> Path:
        return self.work_dir(work_id) / "events.jsonl"

    def rounds_jsonl(self, work_id: str, session_id: str) -> Path:
        return self.work_dir(work_id) / "sessions" / session_id / "rounds.jsonl"

    def manager_json(self, work_id: str) -> Path:
        """这棵子树的变动打给谁;没有 → 父 work(隐式 manager 链)。"""
        return self.work_dir(work_id) / "manager.json"

    def members_json(self, work_id: str) -> Path:
        """人:谁在操作 / 操作过这个 work(不是现场,现场是 sessions.json)。"""
        return self.work_dir(work_id) / "members.json"
