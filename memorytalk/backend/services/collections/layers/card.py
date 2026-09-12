"""card —— 记事层:维基式事实条目(docs/designs/v5/card.md)。对象 = `<path>.card/` 目录:

    readme.md    正文;标题就是目录名;必需
    meta.yaml    context / links[](相关卡的 path)/ issue(讨论页的 path);可无

可改、可删,历史在 git。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .base import Change, Layer, load_yaml


class Card(Layer):
    name = "card"
    files = ["readme.md", "meta.yaml"]
    description = "记事:一条事实,像维基词条;标题是目录名,正文在 readme.md,语境 / 链接 / 讨论页在 meta.yaml。可改、可删,历史在 git。"

    class Meta(BaseModel):
        model_config = ConfigDict(extra="forbid")
        context: str = Field("", description="在哪成立:关于哪个项目 / 用户 / 场景")
        links: list[str] = Field(default_factory=list, description="相关卡的 path")
        issue: str | None = Field(None, description="讨论页:对应的 issue 的 path(卡记 issue,issue 不记卡)")

    def check(self, changes: list[Change], after: dict[str, bytes]) -> str | None:
        for c in changes:
            if c.path == "readme.md":
                if c.new is None:
                    return "readme.md 不能删"
            elif c.path == "meta.yaml":
                if c.new is None:
                    continue
                try:
                    self.Meta.model_validate(load_yaml(c.new))
                except (ValueError, ValidationError) as e:
                    return f"meta.yaml:{e}"
            else:
                return f"{c.path}:card 目录里只能有 readme.md / meta.yaml"
        if "readme.md" not in after:
            return "缺 readme.md"
        return None
