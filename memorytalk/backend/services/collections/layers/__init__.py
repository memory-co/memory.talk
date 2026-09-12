"""每个内置 layer 一个文件(origin / issue / card);用户层来自仓库根 collections.json 里内嵌的 schema(_user.py 编译成 check)。
一个层就是一个 check(changes, after) -> None | str;怎么写一层见 README.md。内置层的顺序在这里定(最底在前);用户层排在它们之上。"""
from __future__ import annotations

from ._layer import Change, Layer
from ._user import from_dict, from_yaml, schema_from_yaml
from .card import LAYER as CARD
from .issue import LAYER as ISSUE
from .origin import LAYER as ORIGIN

BUILTIN: list[Layer] = [ORIGIN, ISSUE, CARD]

__all__ = ["Layer", "Change", "BUILTIN", "from_yaml", "from_dict", "schema_from_yaml"]
