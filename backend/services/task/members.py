"""成员登记:成员 id ↔ URI ↔ server ↔ cwd。唯一权威,身份脱离布局(task.md §3)。"""
from __future__ import annotations

import json

from models.task import Member
from services.store import TasksLayout, atomic_write, read_text

from .tree import now


class MemberNotFound(LookupError):
    pass


class MemberRegistry:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    def _load(self, task_id: str) -> list[Member]:
        text = read_text(self.layout.members_json(task_id))
        return [] if text is None else [Member(**m) for m in json.loads(text)]

    def _save(self, task_id: str, members: list[Member]) -> None:
        atomic_write(self.layout.members_json(task_id),
                     json.dumps([m.model_dump() for m in members], ensure_ascii=False, indent=2) + "\n")

    def list(self, task_id: str) -> list[Member]:
        return self._load(task_id)

    def get(self, task_id: str, member_id: str) -> Member:
        for m in self._load(task_id):
            if m.id == member_id:
                return m
        raise MemberNotFound(f"{task_id}/{member_id}")

    def add(self, task_id: str, uri: str, scheme: str, server: str, cwd: str | None) -> Member:
        members = self._load(task_id)
        n = 1 + max((int(m.id.rsplit("-m", 1)[1]) for m in members if m.id.rsplit("-m", 1)[-1].isdigit()), default=0)
        ts = now()
        m = Member(id=f"{task_id}-m{n}", uri=uri, scheme=scheme, server=server, cwd=cwd,
                   created_at=ts, last_attached=ts)
        members.append(m)
        self._save(task_id, members)
        return m

    def touch(self, task_id: str, member_id: str) -> Member:
        members = self._load(task_id)
        for i, m in enumerate(members):
            if m.id == member_id:
                members[i] = m.model_copy(update={"last_attached": now()})
                self._save(task_id, members)
                return members[i]
        raise MemberNotFound(f"{task_id}/{member_id}")

    def remove(self, task_id: str, member_id: str) -> None:
        members = self._load(task_id)
        if not any(m.id == member_id for m in members):
            raise MemberNotFound(f"{task_id}/{member_id}")
        self._save(task_id, [m for m in members if m.id != member_id])
