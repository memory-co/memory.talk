"""work / user 记录的仓储:业务接口一份,按 provider 的族各实现一份(docs/designs/v5/provider.md §4)。

业务概念(work 节点、画布、工作单元登记、谁动过、manager、事件、收件箱、round、没人管的变动)住在这里;
provider 只见字节 / 表。
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from memorytalk.backend.providers import Column, DatabaseProvider, FileSystemProvider, Table
from memorytalk.backend.providers.db import JSON


class WorkRepo(Protocol):
    # work 节点(可按父 / created_by 列)
    def get_work(self, work_id: str) -> dict | None: ...
    def put_work(self, work_id: str, data: dict) -> None: ...
    def list_works(self, *, parent: str | None = ..., created_by: str | None = None) -> list[dict]: ...
    # 每个 work 下的一份份小记录:canvas / worklets / users / manager
    def get_doc(self, work_id: str, kind: str) -> Any: ...
    def put_doc(self, work_id: str, kind: str, data: Any) -> None: ...
    def del_doc(self, work_id: str, kind: str) -> None: ...
    # 只追加的流:events / inbox;rounds 带 sub = worklet_id
    def append(self, work_id: str, stream: str, line: dict, sub: str | None = None) -> None: ...
    def read(self, work_id: str, stream: str, sub: str | None = None) -> list[dict]: ...
    # 没人管的变动
    def append_unmanaged(self, line: dict) -> None: ...


_MISSING = object()


# ================================================================ fs 版

class FsWorkRepo:
    """目录就是树:works/<id>/…,子 work 在父目录的 subs/ 下——works/<父>/subs/<子>/…。每个 work 目录里:<kind>.json、<stream>.jsonl、worklets/<wid>/rounds.jsonl;根上 unmanaged.jsonl。"""

    def __init__(self, fs: FileSystemProvider) -> None:
        self.fs = fs
        self._dirs: dict[str, str] = {}                 # id → 目录;懒扫,建 work 时登记

    # ---- 目录 ----

    def _scan(self) -> None:
        self._dirs = {}
        for path in self.fs.list("works"):
            if path.endswith("/work.json"):
                d = path[: -len("/work.json")]
                self._dirs[d.rsplit("/", 1)[-1]] = d

    def _dir(self, work_id: str) -> str | None:
        if work_id not in self._dirs:
            self._scan()
        return self._dirs.get(work_id)

    def _doc(self, work_id: str, kind: str) -> str | None:
        d = self._dir(work_id)
        return None if d is None else f"{d}/{kind}.json"

    def _log(self, work_id: str, stream: str, sub: str | None) -> str | None:
        d = self._dir(work_id)
        if d is None:
            return None
        return f"{d}/worklets/{sub}/{stream}.jsonl" if sub else f"{d}/{stream}.jsonl"

    def _read_json(self, path: str | None) -> Any:
        data = None if path is None else self.fs.read(path)
        return None if data is None else json.loads(data)

    def _write_json(self, path: str, data: Any) -> None:
        self.fs.write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())

    # ---- work ----

    def get_work(self, work_id: str) -> dict | None:
        return self._read_json(self._doc(work_id, "work"))

    def put_work(self, work_id: str, data: dict) -> None:
        d = self._dir(work_id)
        if d is None:                                    # 新建:挂在父目录的 subs/ 下,没父就在根上
            parent = data.get("parent")
            pd = self._dir(parent) if parent else None
            d = f"{pd}/subs/{work_id}" if pd else f"works/{work_id}"
            self._dirs[work_id] = d
        self._write_json(f"{d}/work.json", data)

    def list_works(self, *, parent=_MISSING, created_by: str | None = None) -> list[dict]:
        self._scan()
        out = []
        for d in self._dirs.values():
            w = self._read_json(f"{d}/work.json")
            if w is None:
                continue
            if parent is not _MISSING and w.get("parent") != parent:
                continue
            if created_by is not None and w.get("created_by") != created_by:
                continue
            out.append(w)
        return sorted(out, key=lambda w: w["id"])

    # ---- work 下的小记录 / 流 ----

    def get_doc(self, work_id: str, kind: str) -> Any:
        return self._read_json(self._doc(work_id, kind))

    def put_doc(self, work_id: str, kind: str, data: Any) -> None:
        path = self._doc(work_id, kind)
        if path is None:
            raise KeyError(work_id)
        self._write_json(path, data)

    def del_doc(self, work_id: str, kind: str) -> None:
        path = self._doc(work_id, kind)
        if path is not None:
            self.fs.delete(path)

    def append(self, work_id: str, stream: str, line: dict, sub: str | None = None) -> None:
        path = self._log(work_id, stream, sub)
        if path is None:
            raise KeyError(work_id)
        self.fs.append(path, (json.dumps(line, ensure_ascii=False) + "\n").encode())

    def read(self, work_id: str, stream: str, sub: str | None = None) -> list[dict]:
        path = self._log(work_id, stream, sub)
        data = None if path is None else self.fs.read(path)
        if not data:
            return []
        return [json.loads(l) for l in data.decode().splitlines() if l.strip()]

    def append_unmanaged(self, line: dict) -> None:
        self.fs.append("unmanaged.jsonl", (json.dumps(line, ensure_ascii=False) + "\n").encode())


# ================================================================ db 版

class DbWorkRepo:
    """works 表(可查)+ docs 表(每个 work 下的小记录)+ logs 表(只追加,自增 seq)。不写一行 SQL。"""

    def __init__(self, db: DatabaseProvider) -> None:
        self.db = db
        self.works = db.table("works", Column("id", str, primary=True), Column("parent", str, index=True),
                              Column("created_by", str, index=True), Column("status", str), Column("data", JSON))
        self.docs = db.table("work_docs", Column("pk", str, primary=True), Column("work_id", str, index=True),
                             Column("kind", str), Column("data", JSON))
        self.logs = db.table("work_logs", Column("seq", int, primary=True, autoincrement=True),
                             Column("key", str, index=True), Column("line", JSON))

    def get_work(self, work_id: str) -> dict | None:
        r = self.db.select(self.works).where(self.works.c.id == work_id).one()
        return r["data"] if r else None

    def put_work(self, work_id: str, data: dict) -> None:
        cols = dict(parent=data.get("parent"), created_by=data.get("created_by"), status=data.get("status"), data=data)
        if self.db.update(self.works).where(self.works.c.id == work_id).set(**cols).run() == 0:
            self.db.insert(self.works).values(id=work_id, **cols).run()

    def list_works(self, *, parent=_MISSING, created_by: str | None = None) -> list[dict]:
        q = self.db.select(self.works)
        if parent is not _MISSING:
            q = q.where(self.works.c.parent.is_null() if parent is None else self.works.c.parent == parent)
        if created_by is not None:
            q = q.where(self.works.c.created_by == created_by)
        return [r["data"] for r in q.order_by(self.works.c.id.asc()).all()]

    def get_doc(self, work_id: str, kind: str) -> Any:
        r = self.db.select(self.docs).where(self.docs.c.pk == f"{work_id}/{kind}").one()
        return r["data"] if r else None

    def put_doc(self, work_id: str, kind: str, data: Any) -> None:
        pk = f"{work_id}/{kind}"
        if self.db.update(self.docs).where(self.docs.c.pk == pk).set(data=data).run() == 0:
            self.db.insert(self.docs).values(pk=pk, work_id=work_id, kind=kind, data=data).run()

    def del_doc(self, work_id: str, kind: str) -> None:
        self.db.delete(self.docs).where(self.docs.c.pk == f"{work_id}/{kind}").run()

    @staticmethod
    def _key(work_id: str, stream: str, sub: str | None) -> str:
        return f"{work_id}/{stream}" + (f"/{sub}" if sub else "")

    def append(self, work_id: str, stream: str, line: dict, sub: str | None = None) -> None:
        self.db.insert(self.logs).values(key=self._key(work_id, stream, sub), line=line).run()

    def read(self, work_id: str, stream: str, sub: str | None = None) -> list[dict]:
        rows = self.db.select(self.logs).where(self.logs.c.key == self._key(work_id, stream, sub)).order_by(self.logs.c.seq.asc()).all()
        return [r["line"] for r in rows]

    def append_unmanaged(self, line: dict) -> None:
        self.db.insert(self.logs).values(key="unmanaged", line=line).run()

def make_work_repo(store) -> WorkRepo:
    """按 provider 的族选仓储。"""
    if store.family == "fs":
        return FsWorkRepo(store)
    return DbWorkRepo(store)
