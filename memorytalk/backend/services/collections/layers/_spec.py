"""LayerSpec:一个 layer = 名字 + 目录的校验规则(允许哪些文件、每个文件什么格式 / 字段)+ 行为。内置层和用户层都是它。

一个对象是一个目录 `<path>.<layer>/`;目录里允许放什么由 `files` 里的 FileRule 说了算,清单外的文件一律拒。
origin 例外(raw=True):没有目录,路径本身就是文件,不校验。
"""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml
from pydantic import BaseModel

from memorytalk.backend.models.collections import FieldSpec, FileInfo, LayerInfo

_FM = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
FORMATS = ("markdown", "markdown+frontmatter", "yaml", "json", "text")


def _yaml_dump(obj: Any) -> str:
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, default_flow_style=False)


@dataclass
class FileRule:
    pattern: str                                   # 目录内相对路径;可用 * 通配(positions/*.md)
    format: str                                    # markdown | markdown+frontmatter | yaml | json | text
    required: bool = False
    fields: dict[str, FieldSpec] = field(default_factory=dict)
    model: type[BaseModel] | None = None           # yaml / json / frontmatter 的字段校验
    check: Callable[[str, Any, dict[str, Any]], None] | None = None   # (rel, parsed, 全目录 parsed) 额外校验;抛 ValueError
    description: str = ""

    def __post_init__(self) -> None:
        if self.format not in FORMATS:
            raise ValueError(f"文件 {self.pattern}:不支持的格式 {self.format!r}(只有 {', '.join(FORMATS)})")

    @property
    def exact(self) -> bool:
        return "*" not in self.pattern and "?" not in self.pattern

    @property
    def fielded(self) -> bool:
        return self.format in ("markdown+frontmatter", "yaml", "json")

    def matches(self, rel: str) -> bool:
        return fnmatch.fnmatchcase(rel, self.pattern)

    # ---- 编解码 ----

    def parse(self, data: bytes) -> Any:
        text = data.decode("utf-8", "replace")
        if self.format in ("markdown", "text"):
            return text
        if self.format == "json":
            obj = json.loads(text) if text.strip() else {}
        elif self.format == "yaml":
            obj = yaml.safe_load(text) or {}
        else:                                                    # markdown+frontmatter
            m = _FM.match(text)
            obj = (yaml.safe_load(m.group(1)) or {}) if m else {}
            body = m.group(2) if m else text
            if not isinstance(obj, dict):
                raise ValueError("frontmatter 必须是键值表")
            obj["body"] = body.strip("\n")
        if not isinstance(obj, dict):
            raise ValueError("内容必须是键值表")
        return self.model.model_validate(obj).model_dump() if self.model else obj

    def serialize(self, obj: Any) -> bytes:
        if self.format in ("markdown", "text"):
            return (obj if isinstance(obj, str) else str(obj)).encode()
        data = self.model.model_validate(obj).model_dump(exclude_none=True) if self.model else dict(obj)
        if self.format == "json":
            return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        if self.format == "yaml":
            return _yaml_dump(data).encode()
        body = data.pop("body", "") or ""
        meta = {k: v for k, v in data.items() if v not in (None, "", [], {})}
        return ("---\n" + _yaml_dump(meta) + "---\n\n" + body.rstrip("\n") + "\n").encode()

    def info(self) -> FileInfo:
        return FileInfo(pattern=self.pattern, format=self.format, required=self.required, fields=self.fields,
                        description=self.description)


@dataclass
class LayerSpec:
    name: str
    files: list[FileRule] = field(default_factory=list)
    title: str = "dirname"                         # 标题从哪来:dirname | <文件>:<字段>
    refs: dict[str, str] = field(default_factory=dict)
    behaviors: dict[str, Callable] = field(default_factory=dict)
    builtin: bool = False
    description: str = ""
    raw: bool = False                              # origin:没有目录,路径就是文件
    view: Callable[[dict[str, Any], str], Any] | None = None   # (parsed files, path) -> body

    # ---- 形态 ----

    @property
    def suffix(self) -> str | None:
        return None if self.raw else f".{self.name}"

    def obj_dir(self, path: str) -> str:
        return path if self.raw else f"{path}{self.suffix}"

    def split(self, repo_path: str) -> tuple[str, str] | None:
        """仓库路径 → (对象 path, 目录内相对路径);不是本层对象里的文件 → None。"""
        if self.raw:
            return (repo_path, "")
        segs = repo_path.split("/")
        for i, seg in enumerate(segs):
            if seg.endswith(self.suffix) and len(seg) > len(self.suffix):
                return ("/".join(segs[: i + 1])[: -len(self.suffix)], "/".join(segs[i + 1:]))
        return None

    def rule_for(self, rel: str) -> FileRule | None:
        return next((r for r in self.files if r.matches(rel)), None)

    @property
    def fielded_file(self) -> FileRule | None:
        """唯一一个带字段的固定文件(card.md 这种);`data` 写法只对这种层成立。"""
        if len(self.files) == 1 and self.files[0].exact and self.files[0].fielded:
            return self.files[0]
        return None

    # ---- 校验 / 解析 ----

    def validate(self, files: dict[str, bytes]) -> dict[str, Any]:
        """整个目录按规则校验:清单外的文件、格式不对、缺必填、required 的文件不在 → ValueError。返回解析结果。"""
        parsed: dict[str, Any] = {}
        for rel, data in files.items():
            rule = self.rule_for(rel)
            if rule is None:
                raise ValueError(f"{rel}:层 {self.name} 的对象里不允许有这个文件(允许:{', '.join(r.pattern for r in self.files)})")
            try:
                parsed[rel] = rule.parse(data)
            except Exception as e:
                raise ValueError(f"{rel}:{e}") from None
        for rule in self.files:
            if rule.required and not any(rule.matches(rel) for rel in files):
                raise ValueError(f"缺少必需的文件 {rule.pattern}")
        for rel, obj in parsed.items():
            rule = self.rule_for(rel)
            if rule and rule.check:
                try:
                    rule.check(rel, obj, parsed)
                except Exception as e:
                    raise ValueError(f"{rel}:{e}") from None
        return parsed

    def parse(self, files: dict[str, bytes]) -> dict[str, Any]:
        """读:按规则解析,不认识的文件原样给文本,不抛。"""
        out: dict[str, Any] = {}
        for rel, data in files.items():
            rule = self.rule_for(rel)
            try:
                out[rel] = rule.parse(data) if rule else data.decode("utf-8", "replace")
            except Exception:
                out[rel] = data.decode("utf-8", "replace")
        return out

    def body(self, parsed: dict[str, Any], path: str) -> Any:
        if self.view:
            return self.view(parsed, path)
        f = self.fielded_file
        if f and len(self.files) == 1:
            return parsed.get(f.pattern)
        return parsed

    def title_of(self, parsed: dict[str, Any], path: str) -> str:
        if self.title != "dirname" and ":" in self.title:
            file, fld = self.title.split(":", 1)
            obj = parsed.get(file)
            if isinstance(obj, dict) and obj.get(fld):
                return str(obj[fld])
        return path.rsplit("/", 1)[-1]

    def defaults(self) -> dict[str, bytes]:
        """建对象时没给的必需文件:文本类给空文件(git 里目录得有东西)。"""
        return {r.pattern: b"" for r in self.files if r.required and r.exact and r.format in ("markdown", "text")}

    def info(self, order: int) -> LayerInfo:
        return LayerInfo(name=self.name, order=order, builtin=self.builtin, suffix=self.suffix, title=self.title,
                         files=[r.info() for r in self.files], behaviors=sorted(self.behaviors), description=self.description)


def fields_of(model: type[BaseModel], refs: dict[str, str] | None = None) -> dict[str, FieldSpec]:
    """从 pydantic 模型抽一份给 API 看的字段表(内置层用)。"""
    refs = refs or {}
    out = {}
    for name, f in model.model_fields.items():
        t = getattr(f.annotation, "__name__", None) or str(f.annotation)
        t = {"str": "string", "int": "int", "bool": "bool"}.get(t, t)
        if name in refs:
            t = "list[ref]" if t.startswith("list") else "ref"
        out[name] = FieldSpec(type=t, required=f.is_required(), ref=refs.get(name), description=f.description or "")
    return out
