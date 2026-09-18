"""层协议:一份 YAML → 一个 Layer。同一份既是校验规则,也是前端画表单的说明(docs/designs/v5/collections-layer.md)。

    layer: issue
    object: {pattern: ^(?P<name>[^/]+)\\.issue$, name: 问题, under: .*}     # 对象目录叫什么、能放哪
    files:                                                                 # 目录里允许的文件,每种一个正则
      - {pattern: ^readme\\.md$, label: 问题, required: true, format: {fields: {...}, body: markdown}, template: ""}
      - {pattern: ^positions/(?P<name>[^/]+)\\.md$, name: 主张, label: 立场, format: {...}}

每个文件 = frontmatter 字段 + 正文。引擎只看单个文件 + 路径规则,没有跨文件约束。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import yaml

MECHANISM = "manager.json"                    # 机制文件,任何层的任何目录都允许,不进校验
FIELD_TYPES = ("string", "text", "number", "bool", "date", "enum", "ref", "list", "object")
BODY_TYPES = ("markdown", "text")
_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)


@dataclass(frozen=True)
class Change:
    path: str                    # 对象目录内相对路径
    old: bytes | None            # None = 新增
    new: bytes | None            # None = 删除


# ---------------------------------------------------------------- 字段

@dataclass
class Field:
    type: str
    required: bool = False
    description: str = ""
    values: list[str] | None = None            # enum
    layer: str | None = None                   # ref
    item: "Field | None" = None                # list
    fields: dict[str, "Field"] | None = None   # object

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"type": self.type}
        if self.required: d["required"] = True
        if self.description: d["description"] = self.description
        if self.values is not None: d["values"] = self.values
        if self.layer is not None: d["layer"] = self.layer
        if self.item is not None: d["item"] = self.item.to_dict()
        if self.fields is not None: d["fields"] = {k: v.to_dict() for k, v in self.fields.items()}
        return d


def parse_field(where: str, spec: Any, in_list: bool = False) -> Field:
    if not isinstance(spec, dict) or "type" not in spec:
        raise ValueError(f"{where}:字段要写成 {{type: …}}")
    t = str(spec["type"])
    if t not in FIELD_TYPES:
        raise ValueError(f"{where}:不支持的类型 {t!r}(只有 {', '.join(FIELD_TYPES)})")
    f = Field(type=t, required=bool(spec.get("required")), description=str(spec.get("description", "")))
    if t == "enum":
        if not isinstance(spec.get("values"), list) or not spec["values"]:
            raise ValueError(f"{where}:enum 要有 values")
        f.values = [str(v) for v in spec["values"]]
    elif t == "ref":
        if not spec.get("layer"):
            raise ValueError(f"{where}:ref 要有 layer")
        f.layer = str(spec["layer"])
    elif t == "list":
        f.item = parse_field(f"{where}.item", spec.get("item"), in_list=True)
    elif t == "object":
        if not in_list:
            raise ValueError(f"{where}:object 只能出现在 list.item 里")
        if not isinstance(spec.get("fields"), dict) or not spec["fields"]:
            raise ValueError(f"{where}:object 要有 fields")
        f.fields = {}
        for k, v in spec["fields"].items():
            sub = parse_field(f"{where}.{k}", v)
            if sub.type in ("object", "list"):
                raise ValueError(f"{where}.{k}:object 里不能再嵌 {sub.type}")
            f.fields[str(k)] = sub
    for k in spec:
        if k not in ("type", "required", "description", "values", "layer", "item", "fields"):
            raise ValueError(f"{where}:不认识的键 {k!r}")
    return f


def check_value(f: Field, value: Any, where: str) -> str | None:
    if value is None:
        return f"{where}:必填" if f.required else None
    t = f.type
    if t in ("string", "text", "ref"):
        return None if isinstance(value, str) else f"{where}:要是文本"
    if t == "number":
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) else f"{where}:要是数字"
    if t == "bool":
        return None if isinstance(value, bool) else f"{where}:要是 true / false"
    if t == "date":
        if isinstance(value, (date, datetime)):
            return None
        try:
            date.fromisoformat(str(value)[:10]); return None
        except ValueError:
            return f"{where}:要是日期(YYYY-MM-DD)"
    if t == "enum":
        return None if str(value) in (f.values or []) else f"{where}:只能是 {' / '.join(f.values or [])}"
    if t == "list":
        if not isinstance(value, list):
            return f"{where}:要是列表"
        for i, v in enumerate(value):
            if (why := check_value(f.item, v, f"{where}[{i}]")):      # type: ignore[arg-type]
                return why
        return None
    if t == "object":
        if not isinstance(value, dict):
            return f"{where}:要是键值表"
        return check_fields(f.fields or {}, value, where)
    return None


def check_fields(fields: dict[str, Field], data: dict, where: str) -> str | None:
    for k in data:
        if k not in fields:
            return f"{where}:不认识的字段 {k!r}(有:{', '.join(fields) or '无'})"
    for k, f in fields.items():
        if (why := check_value(f, data.get(k), f"{where}.{k}" if where else k)):
            return why
    return None


# ---------------------------------------------------------------- 文件种类 / 对象目录

def _example(pattern: str) -> str:
    """正则 → 给人看 / 给前端代名字的模板:去掉 ^ $,命名组换成 {name},反转义。"""
    s = pattern
    s = s[1:] if s.startswith("^") else s
    s = s[:-1] if s.endswith("$") else s
    s = re.sub(r"\(\?P<name>(?:[^()\\]|\\.)*\)", "{name}", s)
    return re.sub(r"\\(.)", r"\1", s)


@dataclass
class FileKind:
    pattern: str
    label: str
    required: bool = False
    name: str | None = None                      # 带捕获组时:那一段叫什么
    fields: dict[str, Field] | None = None       # None = 纯正文文件
    body: str = "markdown"
    template: str = ""
    regex: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.regex = re.compile(self.pattern)

    @property
    def fixed(self) -> bool:
        return "name" not in self.regex.groupindex

    @property
    def example(self) -> str:
        return _example(self.pattern)

    def match(self, rel: str) -> re.Match | None:
        return self.regex.fullmatch(rel)

    def instantiate(self, name: str) -> str:
        return self.example.replace("{name}", name)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"pattern": self.pattern, "label": self.label, "fixed": self.fixed, "example": self.example,
                             "required": self.required, "format": {"body": self.body}, "template": self.template}
        if self.name: d["name"] = self.name
        if self.fields is not None: d["format"]["fields"] = {k: v.to_dict() for k, v in self.fields.items()}
        return d

    # ---- 单个文件的校验 / 编解码 ----

    def split(self, data: bytes) -> tuple[dict, str]:
        """bytes → (frontmatter 字段, 正文)。"""
        text = data.decode("utf-8", "replace")
        m = _FM.match(text)
        if not m:
            return {}, text
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            raise ValueError("frontmatter 必须是键值表")
        return fm, m.group(2)

    def check(self, data: bytes) -> str | None:
        try:
            fm, _ = self.split(data)
        except (ValueError, yaml.YAMLError) as e:
            return f"frontmatter:{e}"
        if self.fields is None:
            return "这种文件没有字段,不要写 frontmatter" if fm else None
        return check_fields(self.fields, fm, "")

    @staticmethod
    def join(fm: dict, body: str) -> bytes:
        head = ("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n") if fm else ""
        return (head + body.rstrip("\n") + ("\n" if body.strip() else "")).encode()


@dataclass
class ObjectRule:
    pattern: str
    name: str
    under: str
    regex: re.Pattern = field(init=False, repr=False)
    under_regex: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.regex = re.compile(self.pattern)
        self.under_regex = re.compile(self.under)

    @property
    def example(self) -> str:
        return _example(self.pattern)

    def to_dict(self) -> dict:
        return {"pattern": self.pattern, "name": self.name, "under": self.under, "example": self.example}


# ---------------------------------------------------------------- 层

@dataclass
class Layer:
    name: str
    description: str = ""
    builtin: bool = False
    object: ObjectRule | None = None             # None = origin:没有对象目录
    files: list[FileKind] = field(default_factory=list)
    source: dict = field(default_factory=dict)   # YAML 原样

    # ---- 形态 ----

    @property
    def raw(self) -> bool:
        return self.object is None

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

    def kind_of(self, rel: str) -> FileKind | None:
        return next((k for k in self.files if k.match(rel)), None)

    # ---- 校验 ----

    def check_object_path(self, path: str, inside_object: bool) -> str | None:
        """新建对象:目录名匹配 object.pattern、父目录匹配 under、不嵌套。"""
        if self.raw:
            return None
        parent, _, leaf = path.rpartition("/")
        dirname = f"{leaf}{self.suffix}"
        if not self.object.regex.fullmatch(dirname):                      # type: ignore[union-attr]
            return f"对象目录名 {dirname!r} 不合 {self.name} 的规则 {self.object.pattern}"   # type: ignore[union-attr]
        if not self.object.under_regex.fullmatch(parent):                 # type: ignore[union-attr]
            return f"{self.name} 不允许放在 {parent or '/'!r} 下(under: {self.object.under})"  # type: ignore[union-attr]
        if inside_object:
            return "对象不能放在别的对象目录里"
        return None

    def check(self, changes: list[Change], after: dict[str, bytes]) -> str | None:
        """这批改动过不过。None = 过;str = 理由。"""
        if self.raw:
            return None
        for c in changes:
            kind = self.kind_of(c.path)
            if kind is None:
                return f"{c.path}:{self.name} 里只能有 {', '.join(k.example for k in self.files)}"
            if c.new is None:
                if kind.required:
                    return f"{c.path}:必需的文件不能删"
                continue
            if (why := kind.check(c.new)):
                return f"{c.path}:{why}"
        for kind in self.files:
            hits = [p for p in after if kind.match(p)]
            if kind.required and not hits:
                return f"缺 {kind.example}"
            if kind.fixed and len(hits) > 1:
                return f"{kind.example} 只能有一个"
        return None

    # ---- 给 tree 的「这里能建什么」 ----

    def can_create_files(self, rel_dir: str, existing: list[str]) -> list[dict]:
        out = []
        prefix = f"{rel_dir}/" if rel_dir else ""
        for kind in self.files:
            if prefix and not kind.example.startswith(prefix):
                continue
            hits = [p for p in existing if kind.match(p)]
            item = kind.to_dict() | {"existing": hits}
            if kind.fixed and hits:
                item |= {"can": False, "reason": "固定文件,已存在"}
            else:
                item["can"] = True
            out.append(item)
        return out

    def to_dict(self) -> dict:
        return {"layer": self.name, "description": self.description,
                "object": self.object.to_dict() if self.object else None,
                "files": [k.to_dict() for k in self.files]}


# ---------------------------------------------------------------- 载入

def from_dict(doc: dict, builtin: bool = False) -> Layer:
    if not isinstance(doc, dict) or not doc.get("layer"):
        raise ValueError("协议要有 layer: <名字>")
    name = str(doc["layer"])
    for k in doc:
        if k not in ("layer", "description", "object", "files"):
            raise ValueError(f"层 {name}:不认识的键 {k!r}")
    layer = Layer(name=name, description=str(doc.get("description", "")), builtin=builtin, source=doc)
    if "files" not in doc and "object" not in doc:
        return layer                                                         # origin 式:没有对象目录
    obj = doc.get("object") or {}
    for k in obj:
        if k not in ("pattern", "name", "under"):
            raise ValueError(f"层 {name}:object 里不认识的键 {k!r}")
    pattern = str(obj.get("pattern") or f"^(?P<name>[^/]+)\\.{re.escape(name)}$")
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"层 {name}:object.pattern 不是合法正则:{e}") from None
    if "name" not in rx.groupindex or not pattern.endswith(f"\\.{re.escape(name)}$"):
        raise ValueError(f"层 {name}:object.pattern 要带命名组 name 并以 \\.{name}$ 结尾")
    layer.object = ObjectRule(pattern=pattern, name=str(obj.get("name", "name")), under=str(obj.get("under", ".*")))
    kinds: list[FileKind] = []
    for i, fs in enumerate(doc.get("files") or []):
        where = f"层 {name} files[{i}]"
        if not isinstance(fs, dict) or not fs.get("pattern"):
            raise ValueError(f"{where}:要有 pattern")
        for k in fs:
            if k not in ("pattern", "name", "label", "required", "format", "template"):
                raise ValueError(f"{where}:不认识的键 {k!r}")
        try:
            rx = re.compile(str(fs["pattern"]))
        except re.error as e:
            raise ValueError(f"{where}:pattern 不是合法正则:{e}") from None
        groups = set(rx.groupindex)
        if groups - {"name"} or (rx.groups and not groups):
            raise ValueError(f"{where}:捕获组只能有一个,且叫 name")
        fmt = fs.get("format") or {}
        for k in fmt:
            if k not in ("fields", "body"):
                raise ValueError(f"{where}:format 里不认识的键 {k!r}")
        body = str(fmt.get("body", "markdown"))
        if body not in BODY_TYPES:
            raise ValueError(f"{where}:body 只能是 {' / '.join(BODY_TYPES)}")
        fields = None
        if fmt.get("fields") is not None:
            if not isinstance(fmt["fields"], dict):
                raise ValueError(f"{where}:fields 要是键值表")
            fields = {str(k): parse_field(f"{where}.fields.{k}", v) for k, v in fmt["fields"].items()}
        kind = FileKind(pattern=str(fs["pattern"]), label=str(fs.get("label", fs["pattern"])), required=bool(fs.get("required")),
                        name=str(fs["name"]) if fs.get("name") else None, fields=fields, body=body, template=str(fs.get("template", "")))
        if kind.required and not kind.fixed:
            raise ValueError(f"{where}:required 只对固定文件")
        if not kind.fixed and not kind.name:
            raise ValueError(f"{where}:带捕获组的 pattern 要有 name")
        kinds.append(kind)
    for a in kinds:                                                           # 两两不相交:用样例互相试
        for b in kinds:
            if a is not b and b.match(a.instantiate("样例")):
                raise ValueError(f"层 {name}:{a.pattern} 和 {b.pattern} 会匹配同一个路径")
    if not kinds:
        raise ValueError(f"层 {name}:files 不能为空")
    layer.files = kinds
    return layer


def from_yaml(text: str, builtin: bool = False) -> Layer:
    return from_dict(yaml.safe_load(text) or {}, builtin)
