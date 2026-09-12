"""一个层 = 一个校验函数。

    check(changes, after) -> None | str        None = 过;str = 拒绝的理由

changes 是这次提交对**一个对象目录**的 diff(目录内相对路径,old / new 为 None 表示新增 / 删除);
after 是改完之后这个目录的全部文件。看 diff 才能表达「只增不改」,看 after 才能做跨文件约束。
这就是一个 pre-receive hook 的形状;层不认识 API、不认识读法、不认识行为。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import yaml

MECHANISM = "manager.json"       # 机制文件,任何层的任何目录都允许,不进 check


@dataclass(frozen=True)
class Change:
    path: str                    # 目录内相对路径
    old: bytes | None            # None = 新增
    new: bytes | None            # None = 删除


@dataclass
class Layer:
    name: str
    check: Callable[[list[Change], dict[str, bytes]], str | None]
    files: list[str]             # 目录里允许的文件(给人看的清单;真正的规则在 check 里)
    description: str = ""
    builtin: bool = False
    raw: bool = False            # origin:没有目录,路径本身就是文件,不校验
    schema: dict | None = None   # 用户层:它的 YAML(原样);内置层 None

    @property
    def suffix(self) -> str | None:
        return None if self.raw else f".{self.name}"

    def obj_dir(self, path: str) -> str:
        return path if self.raw else f"{path}{self.suffix}"

    def split(self, repo_path: str) -> tuple[str, str] | None:
        """仓库路径 → (对象 path, 目录内相对路径);不是本层对象里的文件 → None。"""
        if self.raw:
            return (repo_path, "")
        segs = repo_path.split("/")
        for i, seg in enumerate(segs):
            if seg.endswith(self.suffix) and len(seg) > len(self.suffix):
                return ("/".join(segs[: i + 1])[: -len(self.suffix)], "/".join(segs[i + 1:]))
        return None


# ---- 给各层的 check 用的小工具 ----

def appended_only(old: bytes, new: bytes) -> bool:
    """new 只是 old 末尾加了内容(允许补上末尾换行)。"""
    o = old.rstrip(b"\n")
    return new.startswith(o) and (len(new) == len(old) or new[len(o):].startswith(b"\n") or not o)


def load_yaml(data: bytes) -> dict:
    obj = yaml.safe_load(data.decode("utf-8", "replace")) or {}
    if not isinstance(obj, dict):
        raise ValueError("必须是键值表")
    return obj
