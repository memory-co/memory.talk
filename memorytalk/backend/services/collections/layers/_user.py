"""用户自定义层:一份 YAML schema → LayerSpec(docs/designs/v5/collections-layer.md)。没有行为。

两种写法都认:
  files:                      # 目录清单:每个文件一条(路径可用 * 通配),各自 format / required / fields
    readme.md: {format: markdown, required: true}
    meta.yaml: {format: yaml, fields: {...}}
  title: dirname | <文件>:<字段>

  format: markdown+frontmatter | json      # 单文件简写:对象目录里只有 <层>.md / <层>.json,字段就是 fields
  title: <字段>
  fields: {...}
"""
from __future__ import annotations

from typing import Any

import yaml
from pydantic import ConfigDict, Field, create_model

from memorytalk.backend.models.collections import FieldSpec
from ._spec import FileRule, LayerSpec

_TYPES: dict[str, Any] = {"string": str, "int": int, "bool": bool, "ref": str,
                          "list[string]": list[str], "list[ref]": list[str]}


def schema_from_yaml(text: str) -> dict:
    doc = yaml.safe_load(text) or {}
    if "layer" not in doc:
        raise ValueError("schema 里要有 layer: <名字>")
    return doc


def from_yaml(text: str) -> LayerSpec:
    doc = schema_from_yaml(text)
    return from_dict(doc["layer"], doc)


def _fields(name: str, fname: str, spec_fields: dict | None, with_body: bool) -> tuple[dict[str, FieldSpec], dict[str, str], type]:
    fields: dict[str, FieldSpec] = {}
    refs: dict[str, str] = {}
    model_fields: dict[str, Any] = {}
    for fld, spec in (spec_fields or {}).items():
        spec = spec or {}
        t = str(spec.get("type", "string"))
        if t not in _TYPES:
            raise ValueError(f"层 {name} 的 {fname} 字段 {fld}:不支持的类型 {t!r}(只有 {', '.join(_TYPES)})")
        fields[fld] = FieldSpec(type=t, required=bool(spec.get("required")), ref=spec.get("layer"),
                                description=str(spec.get("description", "")))
        if t in ("ref", "list[ref]"):
            refs[fld] = spec.get("layer", "")
        py = _TYPES[t]
        model_fields[fld] = (py, ...) if spec.get("required") else (py | None, Field(default=None))
    if with_body:
        model_fields["body"] = (str, Field(default=""))
    model = create_model(f"Layer_{name}_{fname.replace('/', '_').replace('*', 'x').replace('.', '_')}", __config__=ConfigDict(extra="forbid"), **model_fields)  # type: ignore[call-overload]
    return fields, refs, model


def from_dict(name: str, doc: dict) -> LayerSpec:
    """collections.json 里内嵌的 schema → LayerSpec。"""
    rules: list[FileRule] = []
    refs: dict[str, str] = {}
    if "files" in doc:
        for pattern, fs in (doc["files"] or {}).items():
            fs = fs or {}
            fmt = str(fs.get("format", "markdown"))
            fields: dict[str, FieldSpec] = {}
            model = None
            if fs.get("fields"):
                if fmt not in ("markdown+frontmatter", "yaml", "json"):
                    raise ValueError(f"层 {name} 的 {pattern}:格式 {fmt} 没有字段")
                fields, r, model = _fields(name, pattern, fs["fields"], fmt == "markdown+frontmatter")
                refs.update(r)
            rules.append(FileRule(str(pattern), fmt, required=bool(fs.get("required")), fields=fields, model=model,
                                  description=str(fs.get("description", ""))))
        title = str(doc.get("title") or "dirname")
    else:                                                             # 单文件简写
        fmt = "markdown+frontmatter" if str(doc.get("format", "markdown+frontmatter")).startswith("markdown") else "json"
        fname = f"{name}.md" if fmt == "markdown+frontmatter" else f"{name}.json"
        fields, refs, model = _fields(name, fname, doc.get("fields"), fmt == "markdown+frontmatter")
        rules.append(FileRule(fname, fmt, required=True, fields=fields, model=model))
        title = f"{fname}:{doc['title']}" if doc.get("title") else "dirname"
    if not rules:
        raise ValueError(f"层 {name}:files 不能为空")
    if title != "dirname" and ":" not in title:
        raise ValueError(f"层 {name}:title 要写成 dirname 或 <文件>:<字段>")
    return LayerSpec(name=name, files=rules, title=title, refs=refs, builtin=False,
                     description=str(doc.get("description", "")))
