"""origin —— 事实层:任何不带后缀的文件。原文,不校验(上层改不动;这里的写入口给人 / 采集用)。"""
from __future__ import annotations

from .base import Change, Layer


class Origin(Layer):
    name = "origin"
    files: list[str] = []
    description = "事实:外部来的、原样的、未消化的材料。任何不带层后缀的文件都是它。最底层,上层改不动。"

    def check(self, changes: list[Change], after: dict[str, bytes]) -> str | None:
        return None

    # 没有目录:路径本身就是文件
    @property
    def suffix(self) -> str | None:
        return None

    def obj_dir(self, path: str) -> str:
        return path

    def split(self, repo_path: str) -> tuple[str, str] | None:
        return (repo_path, "")
