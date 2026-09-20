"""分层仓库:在 git 原语(git.py)上搭分层拓扑(语义对齐 collectbase:层即分支、路径不相交、stack 是 merge 视图)。

拓扑
    始祖 ●──┬── layer/origin  ●──●      权威。线性,只放这一层的文件
            ├── layer/issue   ●──●
            ├── layer/card    ●
            └── stack         ●──●──●   合并视图:每次层提交后一个 merge 节点(parents = [stack, 层提交]),树 = 各层并集

锚定:根上的 metas.json(整个 metas 的配置 + 层清单,最底在前),始祖提交只有它;git 历史 = 层的变化史。
写:一批 ops → 一个提交,落在声明的层上;守卫先查每个路径的归属(后缀规则 + 各层树的所有权),碰了别的层就拒。
读:一律读 stack 的树。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from memorytalk.backend.models.metas import Revision

from .git import Entry, Git, GrepHit

ANCHOR = "metas.json"


def _dump(cfg: dict) -> bytes:
    return (json.dumps(cfg, ensure_ascii=False, indent=2) + "\n").encode()


class GuardError(RuntimeError):
    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


class Repo:
    stack = "refs/heads/stack"

    def __init__(self, root: Path, author_name: str, author_email: str) -> None:
        self.git = Git(root, author_name, author_email, initial_branch="stack")
        self.root = root
        self._lock = threading.Lock()

    @staticmethod
    def layer_ref(name: str) -> str:
        return f"refs/heads/layer/{name}"

    # ------------------------------------------------------------ 锚定 / 拓扑

    def anchor(self) -> str | None:
        """始祖提交:stack 上最早的那个(写 metas.json 的那次)。"""
        roots = self.git.root_commits(self.stack)
        return roots[0] if roots else None

    def config(self) -> dict | None:
        """metas.json(从 stack 树里读,不读工作区)。"""
        if self.git.resolve(self.stack) is None:
            return None
        data = self.read(ANCHOR)
        return json.loads(data) if data else None

    def layers(self) -> list[str] | None:
        cfg = self.config()
        return [l["name"] for l in cfg["layers"]] if cfg else None

    def ensure_layers(self, names: list[str], builtin: set[str]) -> None:
        """无则建拓扑;有则把缺的层补上(新层分支从始祖出发,metas.json 在最底层更新)。"""
        cur = self.layers()
        if cur is None:
            cfg = {"version": 1, "layers": [{"name": n, "builtin": n in builtin} for n in names]}
            tree = self.git.write_tree({ANCHOR: Entry("100644", self.git.hash_object(_dump(cfg)), ANCHOR)})
            start = self.git.commit_tree(tree, [], f"[{names[0]}] metas: init\n\nlayers: {', '.join(names)}")
            for n in names:
                self.git.update_ref(self.layer_ref(n), start)
            self.git.update_ref(self.stack, start)
            self.git.set_head(self.stack)
            self.git.sync_worktree(self.stack)
            return
        missing = [n for n in names if n not in cur]
        if not missing:
            return
        start = self.anchor()
        for n in missing:
            if self.git.resolve(self.layer_ref(n)) is None:
                self.git.update_ref(self.layer_ref(n), start)
        cfg = self.config()
        cfg["layers"] += [{"name": n, "builtin": n in builtin} for n in missing]
        self.commit(cur[0], f"[{cur[0]}] metas: add layers {', '.join(missing)}", {ANCHOR: _dump(cfg)}, [],
                    layer_of=lambda p: cur[0])

    # ------------------------------------------------------------ 归属

    def owner(self, path: str, layers: list[str]) -> str | None:
        """这个路径现在归哪层:在哪层的树里(始祖里的东西归最底层)。不在任何层 → None。"""
        anchor = self.anchor()
        anchor_paths = set(self.git.tree_map(anchor)) if anchor else set()
        for n in layers:
            if path in self.git.tree_map(self.layer_ref(n)):
                if path in anchor_paths and n != layers[0]:
                    continue
                return n
        return None

    # ------------------------------------------------------------ 读(stack)

    def tree(self, prefix: str = "", rev: str | None = None) -> dict[str, str]:
        if rev is None and self.git.resolve(self.stack) is None:
            return {}
        return {e.path: e.oid for e in self.git.ls_tree(rev or self.stack, prefix)}

    def read(self, path: str, rev: str | None = None) -> bytes | None:
        return self.git.show(rev or self.stack, path)

    def exists(self, path: str) -> bool:
        return self.read(path) is not None

    # ------------------------------------------------------------ 写

    def commit(self, layer: str, message: str, puts: dict[str, bytes], deletes: list[str] = (),
               layer_of=None, author: tuple[str, str] | None = None) -> str:
        """一批 ops → layer/<layer> 上一个提交 + stack 上一个 merge 节点。守卫在这里。"""
        layers = self.layers() or []
        if layer not in layers:
            raise GuardError(f"没有这一层:{layer}(有:{', '.join(layers)})", 400)
        if not puts and not deletes:
            raise GuardError("没有任何改动", 400)
        with self._lock:
            ref = self.layer_ref(layer)
            tip, stack_tip = self.git.resolve(ref), self.git.resolve(self.stack)
            assert tip and stack_tip
            for p in list(puts) + list(deletes):
                p = p.strip("/")
                if not p or p.startswith("../") or "/../" in p:
                    raise GuardError(f"路径不合法:{p}", 400)
                if layer_of and (want := layer_of(p)) != layer:          # 守卫 ①:后缀 / 机制规则
                    raise GuardError(f"{p} 按规则属于层 [{want}],本次提交声明的是 [{layer}]")
                own = self.owner(p, layers)                                # 守卫 ②:已被别的层占了
                if own and own != layer:
                    raise GuardError(f"{p} 属于层 [{own}],本次提交声明的是 [{layer}]")
            # 层分支:在它自己的树上应用 ops
            entries = self.git.tree_map(ref)
            for p in deletes:
                if p not in entries:
                    raise GuardError(f"没有这个文件:{p}", 404)
                entries.pop(p)
            for p, content in puts.items():
                entries[p] = Entry("100644", self.git.hash_object(content), p)
            tree = self.git.write_tree(entries)
            if tree == self.git.tree_of(tip):
                raise GuardError("这批改动没有产生任何变化", 400)
            new = self.git.commit_tree(tree, [tip], message, author)
            self.git.update_ref(ref, new, tip)
            # stack:同一批 ops 应用到并集树上,打 merge 节点(parents = [stack, 层提交]),信息逐字相同
            union = self.git.tree_map(self.stack)
            for p in deletes:
                union.pop(p, None)
            for p in puts:
                union[p] = entries[p]
            merge = self.git.commit_tree(self.git.write_tree(union), [stack_tip, new], message, author)
            self.git.update_ref(self.stack, merge, stack_tip)
            self.git.sync_worktree(self.stack)
            return new

    # ------------------------------------------------------------ 历史 / 检索

    def log(self, ref: str, path: str | None = None, limit: int = 50) -> list[Revision]:
        return self.git.log(ref, path, limit, first_parent=(ref == self.stack))   # stack 的时间线:每个 merge 节点 = 一次层提交

    def log_files(self, path: str | None = None, limit: int = 50, before: str | None = None) -> list[tuple[Revision, list[str]]]:
        """stack 时间线上的提交 + 每次碰的文件;before = 从这个提交的前一个开始(不含)。"""
        ref = f"{before}^" if before else self.stack
        if before and self.git.resolve(ref) is None:
            return []
        return self.git.log_files(ref, path, limit, first_parent=True)

    def grep(self, query: str) -> list[GrepHit]:
        return self.git.grep(query, self.stack)


__all__ = ["Repo", "GuardError", "ANCHOR", "Entry", "GrepHit"]
