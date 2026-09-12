"""issue —— 议事层(docs/designs/v5/issue.md)。对象 = `<path>.issue/` 目录:

    readme.md            问题的展开;纯 markdown;标题就是目录名;必需,可空
    meta.yaml            links[](和别的 issue 的边)+ positions[](manager 的排序)+ summary;可无
    positions/<主张>.md  一个立场一个文件:阐述 + `## 论证` 下一行一条;只增不改、不删、不改名
"""
from __future__ import annotations

import fnmatch
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .base import Change, Layer, appended_only, load_yaml

LinkType = Literal["specializes", "suggested_by", "questions", "replaces", "related"]


class Issue(Layer):
    name = "issue"
    files = ["readme.md", "meta.yaml", "positions/*.md"]
    description = "议事:一个问题(目录名)+ 立场(positions/ 一个一文件,只增不改)+ 论证(立场文件里一行一条,只追加)+ 边和排序(meta.yaml)。"

    class Link(BaseModel):
        type: LinkType
        target: str = Field(min_length=1)

    class Ranked(BaseModel):
        claim: str = Field(min_length=1)
        note: str = ""

    class Meta(BaseModel):
        model_config = ConfigDict(extra="forbid")
        links: list["Issue.Link"] = Field(default_factory=list)
        positions: list["Issue.Ranked"] = Field(default_factory=list)
        summary: str = ""

    @staticmethod
    def claim_of(rel: str) -> str:
        return rel[len("positions/"):-len(".md")]

    def check(self, changes: list[Change], after: dict[str, bytes]) -> str | None:
        for c in changes:
            p = c.path
            if p == "readme.md":
                if c.new is None:
                    return "readme.md 不能删"
            elif p == "meta.yaml":
                if c.new is not None and (why := self._check_meta(c.new, after)):
                    return f"meta.yaml:{why}"
            elif fnmatch.fnmatchcase(p, "positions/*.md"):
                claim = self.claim_of(p)
                if not claim or claim in (".", ".."):
                    return f"{p}:主张(文件名)不能为空"
                if c.new is None:
                    return f"{p}:立场不能删(改主意是加新立场)"
                if c.old is not None and not appended_only(c.old, c.new):
                    return f"{p}:立场只增不改——只能在末尾追加"
            else:
                return f"{p}:issue 目录里只能有 readme.md / meta.yaml / positions/<主张>.md"
        if "readme.md" not in after:
            return "缺 readme.md"
        return None

    def _check_meta(self, data: bytes, after: dict[str, bytes]) -> str | None:
        try:
            meta = self.Meta.model_validate(load_yaml(data)).model_dump()
        except (ValueError, ValidationError) as e:
            return str(e)
        seen = set()
        for l in meta["links"]:
            if (l["type"], l["target"]) in seen:
                return f"links 里重复:{l['type']} {l['target']}"
            seen.add((l["type"], l["target"]))
        claims = {self.claim_of(f) for f in after if fnmatch.fnmatchcase(f, "positions/*.md")}
        for r in meta["positions"]:
            if r["claim"] not in claims:
                return f"positions 里的 {r['claim']!r} 不是 positions/ 下已有的立场"
        return None


Issue.Meta.model_rebuild()
