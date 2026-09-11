"""LayerSpec:一个 layer 的定义 = 名字 + 形态 + schema + 行为。内置层和用户层都是它。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from memorytalk.backend.models.collections import FieldSpec, LayerInfo

_FM = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)


@dataclass
class LayerSpec:
    name: str
    format: str                                  # json | markdown | raw
    model: type[BaseModel] | None = None         # 校验用;raw 没有
    title: str | None = None
    refs: dict[str, str] = field(default_factory=dict)
    fields: dict[str, FieldSpec] = field(default_factory=dict)
    behaviors: dict[str, Callable] = field(default_factory=dict)
    builtin: bool = False
    description: str = ""

    # ---- 形态 ----

    @property
    def suffix(self) -> str | None:
        return None if self.format == "raw" else f".{self.name}"

    @property
    def body_file(self) -> str | None:
        if self.format == "raw":
            return None
        return f"{self.name}.md" if self.format == "markdown" else f"{self.name}.json"

    def obj_dir(self, path: str) -> str:
        return path if self.format == "raw" else f"{path}{self.suffix}"

    def body_path(self, path: str) -> str:
        return path if self.format == "raw" else f"{self.obj_dir(path)}/{self.body_file}"

    def path_of(self, repo_path: str) -> str | None:
        """仓库路径 → 对象 path;不是本层对象的本体文件 → None。"""
        if self.format == "raw":
            return repo_path
        tail = f"{self.suffix}/{self.body_file}"
        return repo_path[: -len(tail)] if repo_path.endswith(tail) else None

    # ---- 编解码 ----

    def parse(self, data: bytes) -> Any:
        text = data.decode("utf-8", "replace")
        if self.format == "raw":
            return text
        if self.format == "json":
            obj = json.loads(text)
        else:
            m = _FM.match(text)
            obj: dict[str, Any] = {}
            body = text
            if m:
                for line in m.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        obj[k.strip()] = _fm_value(k.strip(), v.strip(), self.fields)
                body = m.group(2)
            obj["body"] = body.strip("\n")
        return self.model.model_validate(obj).model_dump() if self.model else obj

    def serialize(self, obj: Any) -> bytes:
        if self.format == "raw":
            return (obj if isinstance(obj, str) else str(obj)).encode()
        data = self.model.model_validate(obj).model_dump(exclude_none=True) if self.model else dict(obj)
        if self.format == "json":
            return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        body = data.pop("body", "") or ""
        lines = ["---"]
        for k, v in data.items():
            if v in (None, "", [], {}):
                continue
            lines.append(f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}")
        lines.append("---")
        return ("\n".join(lines) + "\n\n" + body.rstrip("\n") + "\n").encode()

    def title_of(self, obj: Any, path: str) -> str:
        if self.title and isinstance(obj, dict) and obj.get(self.title):
            return str(obj[self.title])
        return path.rsplit("/", 1)[-1]

    def info(self, order: int) -> LayerInfo:
        return LayerInfo(name=self.name, order=order, builtin=self.builtin, suffix=self.suffix,
                         body=self.body_file, format=self.format, title=self.title, fields=self.fields,
                         behaviors=sorted(self.behaviors), description=self.description)


def _fm_value(key: str, raw: str, fields: dict[str, FieldSpec]) -> Any:
    spec = fields.get(key)
    if spec and spec.type.startswith("list"):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if spec and spec.type == "int":
        return int(raw)
    if spec and spec.type == "bool":
        return raw.lower() in ("true", "yes", "1")
    return raw


def fields_of(model: type[BaseModel], refs: dict[str, str]) -> dict[str, FieldSpec]:
    """从 pydantic 模型抽一份给 API 看的字段表(内置层用)。"""
    out = {}
    for name, f in model.model_fields.items():
        t = getattr(f.annotation, "__name__", None) or str(f.annotation)
        t = {"str": "string", "int": "int", "bool": "bool"}.get(t, t)
        if name in refs:
            t = "list[ref]" if t.startswith("list") else "ref"
        out[name] = FieldSpec(type=t, required=f.is_required(), ref=refs.get(name), description=f.description or "")
    return out
