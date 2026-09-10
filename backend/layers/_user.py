"""用户自定义层:一份 YAML 字段表 → LayerSpec(docs/designs/v5/collections-layer.md)。没有行为。"""
from __future__ import annotations

from typing import Any

import yaml
from pydantic import Field, create_model

from models.collections import FieldSpec
from ._spec import LayerSpec

_TYPES: dict[str, Any] = {"string": str, "int": int, "bool": bool, "ref": str,
                          "list[string]": list[str], "list[ref]": list[str]}


def from_yaml(text: str) -> LayerSpec:
    doc = yaml.safe_load(text) or {}
    name = doc["layer"]
    fmt = "markdown" if str(doc.get("format", "markdown+frontmatter")).startswith("markdown") else "json"
    fields: dict[str, FieldSpec] = {}
    refs: dict[str, str] = {}
    model_fields: dict[str, Any] = {}
    for fname, spec in (doc.get("fields") or {}).items():
        spec = spec or {}
        t = str(spec.get("type", "string"))
        if t not in _TYPES:
            raise ValueError(f"层 {name} 的字段 {fname}:不支持的类型 {t!r}(只有 {', '.join(_TYPES)})")
        fields[fname] = FieldSpec(type=t, required=bool(spec.get("required")), ref=spec.get("layer"),
                                  description=str(spec.get("description", "")))
        if t in ("ref", "list[ref]"):
            refs[fname] = spec.get("layer", "")
        py = _TYPES[t]
        model_fields[fname] = (py, ...) if spec.get("required") else (py | None, Field(default=None))
    if fmt == "markdown":
        model_fields["body"] = (str, Field(default=""))
    model = create_model(f"Layer_{name}", **model_fields)  # type: ignore[call-overload]
    return LayerSpec(name=name, format=fmt, model=model, title=doc.get("title"), refs=refs, fields=fields,
                     builtin=False, description=str(doc.get("description", "")))
