"""user ↔ work:谁动过这个 work。只做可见性,不做权限(docs/designs/v5/user.md §3)。

任何对 work 的操作,只要请求带了身份,就 touch 一笔;「当前在操作」= 最近 ACTIVE_WINDOW 秒内 touch 过,现算。
"""
from __future__ import annotations

from datetime import datetime, timezone

from models.work import WorkUser, WorkUsers, WorkUserView

from .repo import WorkRepo
from .tree import now

ACTIVE_WINDOW = 120  # 秒


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


class WorkUserRegistry:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def _load(self, work_id: str) -> list[WorkUser]:
        return [WorkUser(**m) for m in (self.repo.get_doc(work_id, "users") or [])]

    def touch(self, work_id: str, user: str) -> WorkUser:
        users = self._load(work_id)
        ts = now()
        for i, m in enumerate(users):
            if m.user == user:
                m = m.model_copy(update={"last_seen": ts, "ops": m.ops + 1})
                del users[i]
                break
        else:
            m = WorkUser(user=user, first_seen=ts, last_seen=ts, ops=1)
        users.insert(0, m)            # 最近动过的排最前;同一秒内的并列靠这个顺序分先后
        self.repo.put_doc(work_id, "users", [u.model_dump() for u in users])
        return m

    def list(self, work_id: str, window: int = ACTIVE_WINDOW) -> WorkUsers:
        t = datetime.now(timezone.utc).timestamp()
        views = [WorkUserView(**m.model_dump(), active=(t - _epoch(m.last_seen)) <= window) for m in self._load(work_id)]
        views.sort(key=lambda v: v.last_seen, reverse=True)
        return WorkUsers(current=[v for v in views if v.active], history=views)
