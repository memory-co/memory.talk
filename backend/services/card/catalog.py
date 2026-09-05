"""目录:按目录分层的标题清单(store.md §5:召回 = 给一张目录)。"""
from __future__ import annotations

from models.card import Card, CatalogDir, CatalogEntry


def build_catalog(cards: list[Card], root: str = "", include_deprecated: bool = False) -> CatalogDir:
    root = root.strip("/")
    tree = CatalogDir(dir=root)
    index: dict[str, CatalogDir] = {root: tree}

    def node(dir_: str) -> CatalogDir:
        if dir_ in index:
            return index[dir_]
        parent = dir_.rsplit("/", 1)[0] if "/" in dir_ else root
        if parent == dir_:
            parent = root
        n = CatalogDir(dir=dir_)
        index[dir_] = n
        node(parent).subdirs.append(n)
        return n

    for c in cards:
        if c.status == "deprecated" and not include_deprecated:
            continue
        d = c.id.rsplit("/", 1)[0] if "/" in c.id else ""
        if root and not (d == root or d.startswith(root + "/")):
            continue
        node(d if d else root).cards.append(CatalogEntry(id=c.id, title=c.title, status=c.status))
    return tree
