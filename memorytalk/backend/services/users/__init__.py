"""UserService:user 是注册的顶层对象——有自己的存储(fs / db 仓储),和 work 平级;不做权限(docs/designs/v5/user.md)。
档案是存的;活动统计是现算的派生信息:建了几个 work 看 works.db,动过哪些看 worktrace.db(开过 / 关过段、打过点),
现在在看哪些看 works.viewers,提交数看 metas 的 git。"""
from __future__ import annotations

from memorytalk.backend.models.search import SearchHit

import subprocess
from datetime import datetime, timezone

from typing import TYPE_CHECKING

from memorytalk.backend.models.users import User, UserCreate, UserProfile, UserUpdate, UserView

if TYPE_CHECKING:   # 只做类型:避免 store → users → metas → work → store 的循环导入
    from memorytalk.backend.services.metas import MetasService
    from memorytalk.backend.services.work.repo import TraceRepo, WorkRepo

from .repo import UserRepo


def _z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _now() -> str:
    return _z(datetime.now(timezone.utc))


def _iso(nanos: int) -> str:
    """轨迹里的 Unix 纳秒 → 和 created_at 同一种写法(UTC 到秒,Z 结尾),好放在一起比大小。"""
    return _z(datetime.fromtimestamp(nanos // 1_000_000_000, timezone.utc))


def _git_date(iso: str) -> str:
    """git 的 %aI 带的是提交人当地的时区 → 换成 UTC 同一种写法(只截前 19 位会把当地时间当成 UTC)。"""
    return _z(datetime.fromisoformat(iso.replace("Z", "+00:00"))) if iso else ""


class UserNotFound(LookupError):
    pass


class UserExists(ValueError):
    pass


class UserService:
    def __init__(self, repo: UserRepo, work_repo: "WorkRepo", trace_repo: "TraceRepo", metas: "MetasService") -> None:
        self.repo = repo
        self.works = work_repo
        self.trace = trace_repo
        self.metas = metas

    # ---- 注册 / 档案(存的)----

    def register(self, req: UserCreate) -> User:
        """建账号。密码哈希存进记录,不进 User 模型;admin 这个名字的 role 固定是 admin。"""
        from memorytalk.backend.services.auth import ADMIN, hash_password     # 局部引,避免循环
        if self.repo.get(req.name):
            raise UserExists(req.name)
        u = User(name=req.name, display_name=req.display_name, email=req.email, created_at=_now(),
                 role="admin" if req.name == ADMIN else "member")
        self.repo.put(u.name, u.model_dump() | {"password": hash_password(req.password) if req.password else ""})
        return u

    def get(self, name: str) -> User:
        data = self.repo.get(name)
        if data is None:
            raise UserNotFound(name)
        return User(**data)

    def exists(self, name: str) -> bool:
        return self.repo.get(name) is not None

    def update(self, name: str, req: UserUpdate) -> User:
        data = self.repo.get(name)                       # 整条记录(含密码哈希)改字段再放回,别把密码丢了
        if data is None:
            raise UserNotFound(name)
        for k in ("display_name", "email"):
            v = getattr(req, k)
            if v is not None:
                data[k] = v
        self.repo.put(name, data)
        return User(**data)

    def author(self, name: str | None) -> tuple[str, str] | None:
        """commit author:注册档案里的名字 + 邮箱(空则 <name>@memory.talk)。没带身份 → None(用服务默认名)。"""
        if not name:
            return None
        u = self.get(name)
        return (u.name, u.email or f"{u.name}@memory.talk")

    # ---- 活动统计(派生,现算)----

    def _touched(self, name: str) -> dict[str, int]:
        """这个人在轨迹里出现过的 work → 最后一次的时刻(纳秒)。只看开过 / 关过段、打过点,读和心跳不算。"""
        return self.trace.touched_by(name)

    def _activity(self) -> dict[str, dict]:
        agg: dict[str, dict] = {}

        def bucket(n: str) -> dict:
            return agg.setdefault(n, {"works_created": 0, "works_touched": 0, "commits": 0, "active_works": [], "last_seen": ""})

        for w in self.works.list_works():                     # 按 id 排
            if w["created_by"]:
                b = bucket(w["created_by"])
                b["works_created"] += 1
                b["last_seen"] = max(b["last_seen"], w["created_at"] or "")
            for name in w["viewers"] or []:
                bucket(name)["active_works"].append(w["id"])
        for u in self.repo.list():
            touched = self._touched(u["name"])
            if touched:
                b = bucket(u["name"])
                b["works_touched"] = len(touched)
                b["last_seen"] = max(b["last_seen"], _iso(max(touched.values())))
        out = subprocess.run(["git", "log", "--first-parent", "--format=%an%x1f%aI", "refs/heads/stack"],
                             cwd=self.metas.repo.root, capture_output=True, text=True).stdout
        for line in out.splitlines():
            name, date = (line.split("\x1f") + [""])[:2]
            if name in agg or self.repo.get(name):
                b = bucket(name)
                b["commits"] += 1
                b["last_seen"] = max(b["last_seen"], _git_date(date))
        return agg

    def search(self, q: str, limit: int = 20) -> list[SearchHit]:
        """名字 / 显示名 / 邮箱里含 q 的成员,按活跃排。"""
        needle = q.lower()
        found = [u for u in self.list() if needle in f"{u.name} {u.display_name} {u.email}".lower()]
        return [SearchHit(kind="user", id=u.name, title=u.display_name or u.name, snippet=u.email) for u in found[:limit]]

    def list(self) -> list[UserView]:
        act = self._activity()
        views = [UserView(**u, **act.get(u["name"], {})) for u in self.repo.list()]
        return sorted(views, key=lambda v: (v.last_seen, v.name), reverse=True)

    def profile(self, name: str) -> UserProfile:
        u = self.get(name)
        act = self._activity().get(name, {})
        created = [w["id"] for w in self.works.list_works(created_by=name)]
        touched = sorted(self._touched(name))
        out = subprocess.run(["git", "log", "--first-parent", f"--author=^{name} <", "--format=%H%x1f%aI%x1f%s", "-20", "refs/heads/stack"],
                             cwd=self.metas.repo.root, capture_output=True, text=True).stdout
        commits = [{"sha": a, "date": b, "subject": c} for a, b, c in (l.split("\x1f") for l in out.splitlines() if l)]
        return UserProfile(**u.model_dump(), **act, works_created_ids=created, works_touched_ids=touched, recent_commits=commits)


__all__ = ["UserService", "UserNotFound", "UserExists"]
