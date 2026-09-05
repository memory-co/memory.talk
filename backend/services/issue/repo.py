"""issue 的文件形态:issues/<id>.json。"""
from __future__ import annotations

import json
from pathlib import Path

from models.issue import Issue
from services.store import MemoryLayout, atomic_write, read_text


class IssueRepo:
    def __init__(self, layout: MemoryLayout) -> None:
        self.layout = layout

    def path(self, issue_id: str) -> Path:
        return self.layout.issue_path(issue_id)

    def rel(self, issue_id: str) -> str:
        return self.layout.rel(self.path(issue_id))

    def load(self, issue_id: str) -> Issue | None:
        text = read_text(self.path(issue_id))
        return None if text is None else Issue.model_validate_json(text)

    def save(self, issue: Issue) -> str:
        atomic_write(self.path(issue.id), issue.model_dump_json(indent=2, exclude_none=True) + "\n")
        return self.rel(issue.id)

    def walk(self) -> list[Issue]:
        root = self.layout.issues
        if not root.is_dir():
            return []
        out = []
        for p in sorted(root.glob("*.json")):
            text = read_text(p)
            if text is not None:
                out.append(Issue.model_validate_json(text))
        return out
