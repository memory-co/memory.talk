"""层 = 一份 YAML 协议(protocol.py 的引擎读它校验,前端读它画表单)。
内置层是本目录下的 origin / issue / card 三份 YAML(顺序在 BUILTIN_ORDER 里定,最底在前);
用户层是 `<home>/layers/*.yaml`,一模一样地载入,排在内置层之上,按文件名。怎么写一层见 README.md。"""
from __future__ import annotations

from pathlib import Path

from .protocol import Change, FileKind, Layer, ObjectRule, from_dict, from_yaml

BUILTIN_ORDER = ["origin", "issue", "card"]
_HERE = Path(__file__).parent


def load_builtin() -> list[Layer]:
    return [from_yaml((_HERE / f"{name}.yaml").read_text(encoding="utf-8"), builtin=True) for name in BUILTIN_ORDER]


def load_user(dir_: Path) -> list[Layer]:
    """`<home>/layers/*.yaml`,按文件名排;文件里的 layer 名必须和文件名一致。"""
    out: list[Layer] = []
    if not dir_.is_dir():
        return out
    for file in sorted(list(dir_.glob("*.yaml")) + list(dir_.glob("*.yml"))):
        if file.name.startswith("_"):
            continue
        try:
            layer = from_yaml(file.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ValueError(f"{file}:{e}") from None
        if layer.name != file.stem:
            raise ValueError(f"{file}:文件名和 layer 名不一致({layer.name})")
        out.append(layer)
    return out


__all__ = ["Layer", "FileKind", "ObjectRule", "Change", "BUILTIN_ORDER", "load_builtin", "load_user", "from_dict", "from_yaml"]
