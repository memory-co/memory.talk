"""StoreService:装配存储——按 MEMORY_TALK_STORE 选 provider(fs / sqlite),按族建 work 仓储。
metas 的分层 git 仓库由 services.metas 自己管(它的介质就是 git)。"""
from __future__ import annotations

from memorytalk.backend.config import Config
from memorytalk.backend.providers import load_store
from memorytalk.backend.services.auth.repo import TokenRepo, make_token_repo
from memorytalk.backend.services.users.repo import UserRepo, make_user_repo
from memorytalk.backend.services.work.repo import WorkRepo, make_work_repo


class StoreService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.provider = load_store(config.home)
        self.work_repo: WorkRepo = make_work_repo(self.provider)
        self.user_repo: UserRepo = make_user_repo(self.provider)
        self.token_repo: TokenRepo = make_token_repo(self.provider)


__all__ = ["StoreService"]
