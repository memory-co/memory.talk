"""每个内置 layer 一个文件(origin / issue / card);用户层来自仓库根 collections.json 里内嵌的 schema(_user.py 翻成 LayerSpec)。
内置层的顺序在这里定(最底在前);用户层排在它们之上,顺序按 collections.json 的 layers[]。怎么定义一层见 README.md。"""
from __future__ import annotations

from ._spec import FileRule, LayerSpec
from ._user import from_dict, from_yaml, schema_from_yaml
from .card import LAYER as CARD
from .issue import LAYER as ISSUE
from .origin import LAYER as ORIGIN

BUILTIN: list[LayerSpec] = [ORIGIN, ISSUE, CARD]

__all__ = ["LayerSpec", "FileRule", "BUILTIN", "from_yaml", "from_dict", "schema_from_yaml"]
