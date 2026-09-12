"""目录:某一层的对象按目录树列出标题(store.md §5:召回 = 给一张目录)。"""
from __future__ import annotations

from memorytalk.backend.models.collections import CatalogDir, CatalogEntry


def build(objects: list[tuple[str, str]], root: str = "") -> CatalogDir:
    """objects = [(path, title)]。"""
    root = root.strip("/")
    tree = CatalogDir(dir=root)
    index = {root: tree}

    def node(d: str) -> CatalogDir:
        if d in index:
            return index[d]
        parent = d.rsplit("/", 1)[0] if "/" in d else root
        n = CatalogDir(dir=d)
        index[d] = n
        node(parent if parent != d else root).subdirs.append(n)
        return n

    for path, title in sorted(objects):
        d = path.rsplit("/", 1)[0] if "/" in path else ""
        if root and not (d == root or d.startswith(root + "/")):
            continue
        node(d if d else root).objects.append(CatalogEntry(path=path, title=title))
    return tree
