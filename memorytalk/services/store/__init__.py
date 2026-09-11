"""StoreService:装配存储——按 MEMORY_TALK_STORE 选 provider(fs / sqlite),按族建 work 仓储。
collections 的分层 git 仓库由 services.collections 自己管(它的介质就是 git)。"""
from __future__ import annotations

from memorytalk.config import Config
from memorytalk.providers import load_store
from memorytalk.services.users.repo import UserRepo, make_user_repo
from memorytalk.services.work.repo import WorkRepo, make_work_repo


class StoreService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.provider = load_store(config.home)
        self.work_repo: WorkRepo = make_work_repo(self.provider)
        self.user_repo: UserRepo = make_user_repo(self.provider)


__all__ = ["StoreService"]
