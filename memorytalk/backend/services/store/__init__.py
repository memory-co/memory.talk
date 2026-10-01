"""StoreService:装配存储。work 固定是两个 sqlite——works.db(现在)和 worktrace.db(经过),各一个 provider 实例,
WorkService / MetasService(投递收件箱)/ UserService(统计)共用这一份(docs/designs/v5/work-store.md §2)。
users / auth 仍按 MEMORY_TALK_STORE 选 provider(fs / sqlite)。metas 的分层 git 仓库由 services.metas 自己管(它的介质就是 git)。"""
from __future__ import annotations

from memorytalk.backend.config import Config
from memorytalk.backend.providers import SQLite, load_store
from memorytalk.backend.services.auth.repo import TokenRepo, make_token_repo
from memorytalk.backend.services.users.repo import UserRepo, make_user_repo
from memorytalk.backend.services.work.repo import TraceRepo, WorkRepo


class StoreService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.works_db = SQLite(config.works_db)
        self.worktrace_db = SQLite(config.worktrace_db)
        self.work_repo = WorkRepo(self.works_db)
        self.trace_repo = TraceRepo(self.worktrace_db)
        self.provider = load_store(config.home)                  # users / auth 用
        self.user_repo: UserRepo = make_user_repo(self.provider)
        self.token_repo: TokenRepo = make_token_repo(self.provider)


__all__ = ["StoreService"]
