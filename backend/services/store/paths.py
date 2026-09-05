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
