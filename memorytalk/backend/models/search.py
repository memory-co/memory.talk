"""综合搜索:一个入口,各 service 各出一份命中,汇总成一个结果。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["work", "collection", "user"]


class SearchHit(BaseModel):
    kind: Kind
    id: str = Field(description="work 的 id / 对象的 path / user 的 name")
    title: str
    snippet: str = Field("", description="命中的那一行 / 状态 / 邮箱,给列表看")
    layer: str | None = Field(None, description="collection:哪一层")
    file: str | None = Field(None, description="collection:命中的仓库文件")
    line: int | None = Field(None, description="collection:命中的行号")
    status: str | None = Field(None, description="work:状态")


class SearchResult(BaseModel):
    query: str
    hits: list[SearchHit] = Field(default_factory=list, description="按 kind 分组、组内按各自的顺序(work 新的在前,collection 按 grep,user 按活跃)")
    counts: dict[str, int] = Field(default_factory=dict, description="每种各命中几条(截断前)")
