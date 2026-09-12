"""用户自定义层:一份 YAML 清单编译成一个 check(docs/designs/v5/collections-layer.md)。

    layer: experiment
    files:
      readme.md:   {format: markdown, required: true}
      result.yaml: {format: yaml, fields: {verdict: {type: string, required: true}, issue: {type: ref, layer: issue}}}
      "runs/*.md": {format: markdown, append_only: true}

format:markdown / text 不看内容;yaml / json 解开按 fields 校验(多余键拒)。required 的文件不能缺、不能删;append_only 的只能追加。
"""
from __future__ import annotations

import fnmatch
import json
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from ._layer import Change, Layer, appended_only, load_yaml

_TYPES: dict[str, Any] = {"string": str, "int": int, "bool": bool, "ref": str,
                          "list[string]": list[str], "list[ref]": list[str]}
_FORMATS = ("markdown", "text", "yaml", "json")


def schema_from_yaml(text: str) -> dict:
    doc = yaml.safe_load(text) or {}
    if "layer" not in doc:
        raise ValueError("schema 里要有 layer: <名字>")
    return doc


def from_yaml(text: str) -> Layer:
    doc = schema_from_yaml(text)
    return from_dict(doc["layer"], doc)


def _model(name: str, fname: str, fields: dict) -> type[BaseModel]:
    model_fields: dict[str, Any] = {}
    for fld, spec in (fields or {}).items():
        spec = spec or {}
        t = str(spec.get("type", "string"))
        if t not in _TYPES:
            raise ValueError(f"层 {name} 的 {fname} 字段 {fld}:不支持的类型 {t!r}(只有 {', '.join(_TYPES)})")
        py = _TYPES[t]
        model_fields[fld] = (py, ...) if spec.get("required") else (py | None, Field(default=None))
    return create_model(f"Layer_{name}_{fname}".replace("/", "_").replace("*", "x").replace(".", "_"),
                        __config__=ConfigDict(extra="forbid"), **model_fields)  # type: ignore[call-overload]


def from_dict(name: str, doc: dict) -> Layer:
    """collections.json 里内嵌的 schema → Layer。"""
    rules: list[tuple[str, str, bool, bool, type[BaseModel] | None]] = []     # (pattern, format, required, append_only, model)
    for pattern, fs in (doc.get("files") or {}).items():
        fs = fs or {}
        fmt = str(fs.get("format", "markdown"))
        if fmt not in _FORMATS:
            raise ValueError(f"层 {name} 的 {pattern}:不支持的格式 {fmt!r}(只有 {', '.join(_FORMATS)})")
        model = None
        if fs.get("fields"):
            if fmt not in ("yaml", "json"):
                raise ValueError(f"层 {name} 的 {pattern}:格式 {fmt} 没有字段")
            model = _model(name, str(pattern), fs["fields"])
        rules.append((str(pattern), fmt, bool(fs.get("required")), bool(fs.get("append_only")), model))
    if not rules:
        raise ValueError(f"层 {name}:files 不能为空")

    def rule_for(rel: str):
        return next((r for r in rules if fnmatch.fnmatchcase(rel, r[0])), None)

    def check(changes: list[Change], after: dict[str, bytes]) -> str | None:
        for c in changes:
            r = rule_for(c.path)
            if r is None:
                return f"{c.path}:{name} 目录里只能有 {', '.join(p for p, *_ in rules)}"
            pattern, fmt, required, append_only, model = r
            if c.new is None:
                if required:
                    return f"{c.path}:必需的文件不能删"
                continue
            if append_only and c.old is not None and not appended_only(c.old, c.new):
                return f"{c.path}:只能在末尾追加"
            if fmt in ("yaml", "json"):
                try:
                    obj = load_yaml(c.new) if fmt == "yaml" else json.loads(c.new.decode("utf-8", "replace") or "{}")
                    if model:
                        model.model_validate(obj)
                except (ValueError, ValidationError) as e:
                    return f"{c.path}:{e}"
        for pattern, fmt, required, *_ in rules:
            if required and not any(fnmatch.fnmatchcase(f, pattern) for f in after):
                return f"缺 {pattern}"
        return None

    return Layer(name=name, check=check, files=[p for p, *_ in rules], builtin=False,
                 description=str(doc.get("description", "")), schema={k: v for k, v in doc.items() if k != "layer"})
