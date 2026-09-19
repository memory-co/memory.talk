"""token 记录的仓储:fs auth/tokens/<sha256>.json;db auth_tokens 表。记的是 token 的哈希 → {user, created_at}。"""
from __future__ import annotations

import json
from typing import Protocol

from memorytalk.backend.providers import Column, DatabaseProvider, FileSystemProvider
from memorytalk.backend.providers.db import JSON


class TokenRepo(Protocol):
    def get(self, digest: str) -> dict | None: ...
    def put(self, digest: str, data: dict) -> None: ...
    def delete(self, digest: str) -> None: ...
    def list(self) -> list[tuple[str, dict]]: ...


class FsTokenRepo:
    def __init__(self, fs: FileSystemProvider) -> None:
        self.fs = fs

    @staticmethod
    def _p(digest: str) -> str:
        return f"auth/tokens/{digest}.json"

    def get(self, digest: str) -> dict | None:
        data = self.fs.read(self._p(digest))
        return None if data is None else json.loads(data)

    def put(self, digest: str, data: dict) -> None:
        self.fs.write(self._p(digest), (json.dumps(data, ensure_ascii=False) + "\n").encode())

    def delete(self, digest: str) -> None:
        self.fs.delete(self._p(digest))

    def list(self) -> list[tuple[str, dict]]:
        out = []
        for path in self.fs.list("auth/tokens"):
            if path.endswith(".json"):
                data = self.fs.read(path)
                if data:
                    out.append((path.rsplit("/", 1)[-1][:-5], json.loads(data)))
        return out


class DbTokenRepo:
    def __init__(self, db: DatabaseProvider) -> None:
        self.db = db
        self.tokens = db.table("auth_tokens", Column("digest", str, primary=True), Column("data", JSON))

    def get(self, digest: str) -> dict | None:
        r = self.db.select(self.tokens).where(self.tokens.c.digest == digest).one()
        return r["data"] if r else None

    def put(self, digest: str, data: dict) -> None:
        if self.db.update(self.tokens).where(self.tokens.c.digest == digest).set(data=data).run() == 0:
            self.db.insert(self.tokens).values(digest=digest, data=data).run()

    def delete(self, digest: str) -> None:
        self.db.delete(self.tokens).where(self.tokens.c.digest == digest).run()

    def list(self) -> list[tuple[str, dict]]:
        return [(r["digest"], r["data"]) for r in self.db.select(self.tokens).all()]


def make_token_repo(store) -> TokenRepo:
    return FsTokenRepo(store) if store.family == "fs" else DbTokenRepo(store)
