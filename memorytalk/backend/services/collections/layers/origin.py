"""origin —— 事实层:任何不带后缀的文件。原文,不校验(上层改不动;这里的写入口给人 / 采集用)。"""
from __future__ import annotations

from ._layer import Layer

LAYER = Layer(
    name="origin", raw=True, builtin=True, files=[],
    check=lambda changes, after: None,
    description="事实:外部来的、原样的、未消化的材料。任何不带层后缀的文件都是它。最底层,上层改不动。",
)
