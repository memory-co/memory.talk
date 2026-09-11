"""manager.json:目录绑 work;变动往上找最近的一个,打到那个 work 的收件箱(docs/designs/v5/manager.md)。"""
from __future__ import annotations

import json

from memorytalk.models.collections import Manager

FILE = "manager.json"


def parents(path: str) -> list[str]:
    """一个仓库路径的所有祖先目录,由近到远,最后是 ''(根)。"""
    out = []
    p = path.rstrip("/")
    while "/" in p:
        p = p.rsplit("/", 1)[0]
        out.append(p)
    out.append("")
    return out


def manager_path(dir_: str) -> str:
    return f"{dir_}/{FILE}" if dir_ else FILE


class ManagerIndex:
    """从 stack 树里读出所有 manager.json 的 {目录: work}。每次用现读,量小。"""

    def __init__(self, repo) -> None:
        self.repo = repo

    def all(self) -> dict[str, str]:
        out = {}
        for path in self.repo.tree():
            if path == FILE or path.endswith("/" + FILE):
                data = self.repo.read(path)
                try:
                    work = json.loads(data or b"{}").get("work")
                except json.JSONDecodeError:
                    work = None
                if work:
                    out[path[: -len(FILE)].rstrip("/")] = work
        return out

    def resolve(self, path: str) -> Manager | None:
        """path(文件或目录)归谁管:最近的祖先目录(含自己,若它是目录)。"""
        table = self.all()
        for d in [path.rstrip("/"), *parents(path)]:
            if d in table:
                return Manager(dir=d, work=table[d])
        return None
