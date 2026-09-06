"""成员:谁在操作 / 操作过这个 task。只做可见性,不做权限(docs/works/v5/member.md)。

任何对 task 的操作,只要请求带了身份,就 touch 一笔;「当前在操作」= 最近 ACTIVE_WINDOW 秒内 touch 过,现算。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from models.task import Member, Members, MemberView
from services.store import TasksLayout, atomic_write, read_text

from .tree import now

ACTIVE_WINDOW = 120  # 秒


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


class MemberRegistry:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    def _load(self, task_id: str) -> list[Member]:
        text = read_text(self.layout.members_json(task_id))
        return [] if text is None else [Member(**m) for m in json.loads(text)]

    def _save(self, task_id: str, members: list[Member]) -> None:
        atomic_write(self.layout.members_json(task_id),
                     json.dumps([m.model_dump() for m in members], ensure_ascii=False, indent=2) + "\n")

    def touch(self, task_id: str, user: str) -> Member:
        members = self._load(task_id)
        ts = now()
        for i, m in enumerate(members):
            if m.user == user:
                members[i] = m.model_copy(update={"last_seen": ts, "ops": m.ops + 1})
                self._save(task_id, members)
                return members[i]
        m = Member(user=user, first_seen=ts, last_seen=ts, ops=1)
        members.append(m)
        self._save(task_id, members)
        return m

    def list(self, task_id: str, window: int = ACTIVE_WINDOW) -> Members:
        t = datetime.now(timezone.utc).timestamp()
        views = [MemberView(**m.model_dump(), active=(t - _epoch(m.last_seen)) <= window) for m in self._load(task_id)]
        views.sort(key=lambda v: v.last_seen, reverse=True)
        return Members(current=[v for v in views if v.active], history=views)
