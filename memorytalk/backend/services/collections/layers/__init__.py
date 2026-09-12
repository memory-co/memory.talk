"""每个内置 layer 一个类(Origin / Issue / Card);用户层是 `<home>/layers/*.py` 里一模一样的 Layer 子类,启动时载入。
一个层就是 Layer 接口的一个实现:check(changes, after) -> None | str;怎么写一层见 README.md。内置层的顺序在这里定(最底在前);用户层排在它们之上,按文件名。"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

from .base import Change, Layer, appended_only, load_yaml
from .card import Card
from .issue import Issue
from .origin import Origin

BUILTIN: list[Layer] = [Origin(), Issue(), Card()]


def load_user(dir_: Path) -> list[Layer]:
    """`<home>/layers/*.py`:每个文件里定义的 Layer 子类各一个实例(builtin=False),按文件名排。"""
    out: list[Layer] = []
    if not dir_.is_dir():
        return out
    for file in sorted(dir_.glob("*.py")):
        if file.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"memorytalk_user_layers.{file.stem}", file)
        mod = importlib.util.module_from_spec(spec)                       # type: ignore[arg-type]
        spec.loader.exec_module(mod)                                      # type: ignore[union-attr]
        classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
                   if issubclass(c, Layer) and c is not Layer and c.__module__ == mod.__name__]
        if not classes:
            raise ValueError(f"{file}:里面没有 Layer 的子类")
        for cls in classes:
            layer = cls()
            layer.builtin = False
            out.append(layer)
    return out


__all__ = ["Layer", "Change", "BUILTIN", "load_user", "appended_only", "load_yaml"]
