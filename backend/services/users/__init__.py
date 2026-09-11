"""UserService:user 是顶层对象,但不注册——在系统里出现过的名字就是 user(docs/designs/v5/user.md)。
从 work(created_by / users 名单)和 collections(commit author)里汇总出来。"""
from __future__ import annotations

import subprocess
from collections import defaultdict
from datetime import datetime, timezone

from models.users import User, UserProfile
from services.collections import CollectionsService
from services.work.repo import WorkRepo
from services.work.users import ACTIVE_WINDOW


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


class UserNotFound(LookupError):
    pass


class UserService:
    def __init__(self, work_repo: WorkRepo, collections: CollectionsService) -> None:
        self.repo = work_repo
        self.collections = collections

    def _authors(self) -> dict[str, tuple[int, str]]:
        """collections 里每个 author 的提交数和最近一次时间(只算 stack 的 first-parent,即每次层提交)。"""
        out = subprocess.run(["git", "log", "--first-parent", "--format=%an%x1f%aI", "refs/heads/stack"],
                             cwd=self.collections.repo.root, capture_output=True, text=True).stdout
        agg: dict[str, tuple[int, str]] = {}
        for line in out.splitlines():
            name, date = (line.split("\x1f") + [""])[:2]
            if name.endswith("memory.talk") and "@" not in name and name == self.collections.config.git_author_name:
                continue                                    # 服务默认名 = 匿名,不算 user
            n, last = agg.get(name, (0, ""))
            agg[name] = (n + 1, max(last, date))
        return agg

    def list(self) -> list[User]:
        seen: dict[str, dict] = defaultdict(lambda: {"works_created": 0, "works_touched": 0, "commits": 0, "last_seen": ""})
        now = datetime.now(timezone.utc).timestamp()
        for w in self.repo.list_works():
            if w.get("created_by"):
                u = seen[w["created_by"]]
                u["works_created"] += 1
                u["last_seen"] = max(u["last_seen"], w.get("created_at", ""))
            for m in self.repo.get_doc(w["id"], "users") or []:
                u = seen[m["user"]]
                u["works_touched"] += 1
                u["last_seen"] = max(u["last_seen"], m["last_seen"])
                if now - _epoch(m["last_seen"]) <= ACTIVE_WINDOW:
                    u.setdefault("active_works", []).append(w["id"])
        for name, (n, last) in self._authors().items():
            u = seen[name]
            u["commits"] = n
            u["last_seen"] = max(u["last_seen"], last[:19].replace("T", "T") if last else "")
        users = [User(name=name, active_works=sorted(set(d.pop("active_works", []))), **d) for name, d in seen.items()]
        return sorted(users, key=lambda u: u.last_seen, reverse=True)

    def get(self, name: str) -> UserProfile:
        users = {u.name: u for u in self.list()}
        if name not in users:
            raise UserNotFound(name)
        u = users[name]
        created = [w["id"] for w in self.repo.list_works(created_by=name)]
        touched = [w["id"] for w in self.repo.list_works() if any(m["user"] == name for m in (self.repo.get_doc(w["id"], "users") or []))]
        out = subprocess.run(["git", "log", "--first-parent", f"--author={name} <", "--format=%H%x1f%aI%x1f%s", "-20", "refs/heads/stack"],
                             cwd=self.collections.repo.root, capture_output=True, text=True).stdout
        commits = [{"sha": a, "date": b, "subject": c} for a, b, c in (l.split("\x1f") for l in out.splitlines() if l)]
        return UserProfile(**u.model_dump(), works_created_ids=created, works_touched_ids=touched, recent_commits=commits)


__all__ = ["UserService", "UserNotFound"]
