"""一个层 = Layer 接口的一个实现:一个 check。

    check(changes, after) -> None | str        None = 过;str = 拒绝的理由(原样报给调用方)

changes 是这次提交对**一个对象目录**的 diff(目录内相对路径,old / new 为 None 表示新增 / 删除);
after 是改完之后这个目录的全部文件。看 diff 才能表达「只增不改」,看 after 才能做跨文件约束。
这就是一个 pre-receive hook 的形状;层不认识 API、不认识读法、没有行为、没有状态(一个实例服务所有对象)。
形态(后缀、目录、路径拆分)从 name 派生,写在基类;子类只管 name / files / check。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import yaml

MECHANISM = "manager.json"       # 机制文件,任何层的任何目录都允许,不进 check


@dataclass(frozen=True)
class Change:
    path: str                    # 目录内相对路径
    old: bytes | None            # None = 新增
    new: bytes | None            # None = 删除


class Layer(ABC):
    name: str                    # 子类声明;= 分支 layer/<name>、后缀 .<name>、提交前缀 [<name>]
    files: list[str] = []        # 目录里允许的文件(给人看的清单;真正的规则在 check 里)
    description: str = ""
    builtin: bool = True         # 用户层(<home>/layers/*.py)载入时置 False

    @abstractmethod
    def check(self, changes: list[Change], after: dict[str, bytes]) -> str | None:
        """这批改动过不过。"""

    # ---- 形态:从 name 派生。origin 覆盖(它没有目录) ----

    @property
    def suffix(self) -> str | None:
        return f".{self.name}"

    def obj_dir(self, path: str) -> str:
        return f"{path}{self.suffix}"

    def split(self, repo_path: str) -> tuple[str, str] | None:
        """仓库路径 → (对象 path, 目录内相对路径);不是本层对象里的文件 → None。"""
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
