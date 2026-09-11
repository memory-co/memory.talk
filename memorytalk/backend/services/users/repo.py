"""user 记录的仓储:业务接口一份,按 provider 的族各实现一份(provider.md §4)。fs:users/<name>.json;db:users 表。"""
from __future__ import annotations

import json
from typing import Protocol

from memorytalk.backend.providers import Column, DatabaseProvider, FileSystemProvider
from memorytalk.backend.providers.db import JSON


class UserRepo(Protocol):
    def get(self, name: str) -> dict | None: ...
    def put(self, name: str, data: dict) -> None: ...
    def delete(self, name: str) -> None: ...
    def list(self) -> list[dict]: ...


class FsUserRepo:
    def __init__(self, fs: FileSystemProvider) -> None:
        self.fs = fs

    @staticmethod
    def _p(name: str) -> str:
        return f"users/{name}.json"

    def get(self, name: str) -> dict | None:
        data = self.fs.read(self._p(name))
        return None if data is None else json.loads(data)

    def put(self, name: str, data: dict) -> None:
        self.fs.write(self._p(name), (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())

    def delete(self, name: str) -> None:
        self.fs.delete(self._p(name))

    def list(self) -> list[dict]:
        out = []
        for path in self.fs.list("users"):
            if path.endswith(".json") and path.count("/") == 1:
                data = self.fs.read(path)
                if data:
                    out.append(json.loads(data))
        return sorted(out, key=lambda u: u["name"])


class DbUserRepo:
    def __init__(self, db: DatabaseProvider) -> None:
        self.db = db
        self.users = db.table("users", Column("name", str, primary=True), Column("data", JSON))

    def get(self, name: str) -> dict | None:
        r = self.db.select(self.users).where(self.users.c.name == name).one()
        return r["data"] if r else None

    def put(self, name: str, data: dict) -> None:
        if self.db.update(self.users).where(self.users.c.name == name).set(data=data).run() == 0:
            self.db.insert(self.users).values(name=name, data=data).run()

    def delete(self, name: str) -> None:
        self.db.delete(self.users).where(self.users.c.name == name).run()

    def list(self) -> list[dict]:
        return [r["data"] for r in self.db.select(self.users).order_by(self.users.c.name.asc()).all()]


def make_user_repo(store) -> UserRepo:
    return FsUserRepo(store) if store.family == "fs" else DbUserRepo(store)
