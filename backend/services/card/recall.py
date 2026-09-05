"""召回:把目录渲染成一段能直接注入 agent 上下文的文本。"""
from __future__ import annotations

from models.card import CatalogDir


def render_catalog(tree: CatalogDir, indent: int = 0) -> str:
    lines: list[str] = []
    pad = "  " * indent
    if tree.dir:
        lines.append(f"{pad}{tree.dir}/")
        indent += 1
        pad = "  " * indent
    for e in tree.cards:
        lines.append(f"{pad}- {e.title}  ({e.id})")
    for sub in tree.subdirs:
        lines.append(render_catalog(sub, indent))
    return "\n".join(l for l in lines if l)
