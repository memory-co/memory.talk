"""每个内置 layer 一个类(Origin / Issue / Card),用户层是 UserLayer(规则从 collections.json 里内嵌的 YAML 来)。
一个层就是 Layer 接口的一个实现:check(changes, after) -> None | str;怎么写一层见 README.md。内置层的顺序在这里定(最底在前);用户层排在它们之上。"""
from __future__ import annotations

from ._user import UserLayer, from_dict, from_yaml, schema_from_yaml
from .base import Change, Layer
from .card import Card
from .issue import Issue
from .origin import Origin

BUILTIN: list[Layer] = [Origin(), Issue(), Card()]

__all__ = ["Layer", "Change", "UserLayer", "BUILTIN", "from_yaml", "from_dict", "schema_from_yaml"]
