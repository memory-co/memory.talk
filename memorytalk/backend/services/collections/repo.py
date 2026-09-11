"""Collections 仓库:分层 git,自己实现(语义对齐 collectbase:层即分支、路径不相交、stack 是 merge 视图)。

拓扑
    始祖 ●──┬── layer/origin  ●──●      权威。线性,只放这一层的文件
            ├── layer/issue   ●──●
            ├── layer/card    ●
            └── stack         ●──●──●   合并视图:每次层提交后打一个 merge 节点(parents = [stack, 层提交]),树 = 各层并集

写:一批 ops → 一个提交,落在声明的层上;守卫先查每个路径的归属(后缀规则 + 各层树的所有权),
    碰了别的层的路径就拒绝。再把同一批 ops 应用到 stack 的树上,打 merge 节点。
读:一律读 stack 的树。全部 plumbing,不碰工作树(HEAD 指向 stack,提交后 reset 让工作树跟上,方便人 ls)。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from memorytalk.backend.models.collections import Revision

ANCHOR = "layers"                     # 根上的层清单:一行一个,最底在前


class GuardError(RuntimeError):
    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class GrepHit:
    file: str
    line: int
    text: str


@dataclass(frozen=True)
class Entry:
    mode: str
    oid: str
    path: str


class Repo:
    def __init__(self, root: Path, author_name: str, author_email: str) -> None:
        self.root = root
        self._lock = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            self._git("init", "-q", "-b", "stack")
        for k, v in (("user.name", author_name), ("user.email", author_email), ("core.quotepath", "false")):
            self._git("config", k, v)

    # ------------------------------------------------------------ git 原语

    def _run(self, *args: str, stdin: bytes | None = None, check: bool = True, env: dict | None = None) -> bytes:
        p = subprocess.run(["git", *args], cwd=self.root, input=stdin, capture_output=True,
                           env={**os.environ, **(env or {})})
        if check and p.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {p.stderr.decode(errors='replace').strip()}")
        return p.stdout

    def _git(self, *args: str, **kw) -> str:
        return self._run(*args, **kw).decode("utf-8", "replace")

    def resolve(self, ref: str) -> str | None:
        p = subprocess.run(["git", "rev-parse", "--verify", "-q", ref], cwd=self.root, capture_output=True, text=True)
        return p.stdout.strip() or None

    def ls_tree(self, rev: str, prefix: str = "") -> list[Entry]:
        args = ["ls-tree", "-r", "-z", rev] + (["--", prefix] if prefix else [])
        out = self._run(*args, check=False)
        entries = []
        for chunk in out.split(b"\0"):
            if not chunk:
                continue
            meta, path = chunk.split(b"\t", 1)
            mode, kind, oid = meta.decode().split()
            if kind == "blob":
                entries.append(Entry(mode, oid, path.decode("utf-8", "surrogateescape")))
        return entries

    def tree_map(self, rev: str, prefix: str = "") -> dict[str, Entry]:
        return {e.path: e for e in self.ls_tree(rev, prefix)}

    def hash_object(self, data: bytes) -> str:
        return self._git("hash-object", "-w", "--stdin", stdin=data).strip()

    def write_tree(self, entries: dict[str, Entry]) -> str:
        fd, idx = tempfile.mkstemp(prefix="cb-index-", dir=self.root / ".git")
        os.close(fd)
        os.unlink(idx)
        payload = b"".join(f"{e.mode} blob {e.oid}\t{e.path}".encode("utf-8", "surrogateescape") + b"\0"
                           for e in entries.values())
        try:
            self._run("update-index", "-z", "--index-info", stdin=payload, env={"GIT_INDEX_FILE": idx})
            return self._git("write-tree", env={"GIT_INDEX_FILE": idx}).strip()
        finally:
            try:
                os.unlink(idx)
            except FileNotFoundError:
                pass

    def commit_tree(self, tree: str, parents: list[str], message: str, author: tuple[str, str] | None = None) -> str:
        """author = (名字, 邮箱):做这个动作的 user 的档案(commit 的 author 就是人,user.md §5);没有则用仓库配置的默认名。"""
        args = ["commit-tree", tree]
        for p in parents:
            args += ["-p", p]
        env = {"GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1]} if author else None
        return self._git(*args, stdin=message.encode(), env=env).strip()

    def update_ref(self, ref: str, new: str, old: str | None = None) -> None:
        args = ["update-ref", ref, new] + ([old] if old else [])
        self._git(*args)

    # ------------------------------------------------------------ 拓扑

    @staticmethod
    def layer_ref(name: str) -> str:
        return f"refs/heads/layer/{name}"

    stack = "refs/heads/stack"

    def anchor(self) -> str | None:
        """始祖提交:stack 上最早的那个(写 layers 的那次)。"""
        sha = self._git("rev-list", "--max-parents=0", self.stack, check=False).split()
        return sha[0] if sha else None

    def layers(self) -> list[str] | None:
        if self.resolve(self.stack) is None:
            return None
        data = self.read(ANCHOR)
        return [l.strip() for l in data.decode().splitlines() if l.strip()] if data else None

    def ensure_layers(self, names: list[str]) -> None:
        """无则建拓扑;有则把缺的层补上(新层分支从始祖出发,layers 文件在最底层更新)。"""
        cur = self.layers()
        if cur is None:
            text = "\n".join(names) + "\n"
            tree = self.write_tree({ANCHOR: Entry("100644", self.hash_object(text.encode()), ANCHOR)})
            start = self.commit_tree(tree, [], f"[{names[0]}] collections: init\n\nlayers: {', '.join(names)}")
            for n in names:
                self.update_ref(self.layer_ref(n), start)
            self.update_ref(self.stack, start)
            self._git("symbolic-ref", "HEAD", self.stack)
            self._sync_worktree()
            return
        missing = [n for n in names if n not in cur]
        if not missing:
            return
        start = self.anchor()
        for n in missing:
            if self.resolve(self.layer_ref(n)) is None:
                self.update_ref(self.layer_ref(n), start)
        new = [*cur, *missing]
        self.commit(cur[0], f"[{cur[0]}] collections: add layers {', '.join(missing)}",
                    {ANCHOR: ("\n".join(new) + "\n").encode()}, [], layer_of=lambda p: cur[0])

    # ------------------------------------------------------------ 归属

    def owner(self, path: str, layers: list[str]) -> str | None:
        """这个路径现在归哪层:在哪层的树里(始祖里的东西归最底层)。不在任何层 → None。"""
        anchor = self.anchor()
        anchor_paths = set(self.tree_map(anchor)) if anchor else set()
        for n in layers:
            if path in self.tree_map(self.layer_ref(n)):
                if path in anchor_paths and n != layers[0]:
                    continue
                return n
        return None

    # ------------------------------------------------------------ 读

    def tree(self, prefix: str = "") -> dict[str, str]:
        if self.resolve(self.stack) is None:
            return {}
        return {e.path: e.oid for e in self.ls_tree(self.stack, prefix)}

    def read(self, path: str, rev: str | None = None) -> bytes | None:
        p = subprocess.run(["git", "show", f"{rev or self.stack}:{path}"], cwd=self.root, capture_output=True)
        return p.stdout if p.returncode == 0 else None

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
            tip = self.resolve(ref)
            stack_tip = self.resolve(self.stack)
            assert tip and stack_tip
            # 守卫 ①:后缀 / 机制规则说这个路径该归哪层
            for p in list(puts) + list(deletes):
                p = p.strip("/")
                if not p or p.startswith("../") or "/../" in p:
                    raise GuardError(f"路径不合法:{p}", 400)
                if layer_of and (want := layer_of(p)) != layer:
                    raise GuardError(f"{p} 按规则属于层 [{want}],本次提交声明的是 [{layer}]")
                # 守卫 ②:已经被别的层占了
                own = self.owner(p, layers)
                if own and own != layer:
                    raise GuardError(f"{p} 属于层 [{own}],本次提交声明的是 [{layer}]")
            # 层分支:在它自己的树上应用 ops
            entries = self.tree_map(ref)
            for p in deletes:
                if p not in entries:
                    raise GuardError(f"没有这个文件:{p}", 404)
                entries.pop(p)
            for p, content in puts.items():
                entries[p] = Entry("100644", self.hash_object(content), p)
            tree = self.write_tree(entries)
            if tree == self._git("rev-parse", f"{tip}^{{tree}}").strip():
                raise GuardError("这批改动没有产生任何变化", 400)
            new = self.commit_tree(tree, [tip], message, author)
            self.update_ref(ref, new, tip)
            # stack:同一批 ops 应用到并集树上,打 merge 节点(parents = [stack, 层提交]),信息逐字相同
            union = self.tree_map(self.stack)
            for p in deletes:
                union.pop(p, None)
            for p in puts:
                union[p] = entries[p]
            merge = self.commit_tree(self.write_tree(union), [stack_tip, new], message, author)
            self.update_ref(self.stack, merge, stack_tip)
            self._sync_worktree()
            return new

    def _sync_worktree(self) -> None:
        """工作树跟上 stack(只为了人能 ls / cat;服务从不读它)。"""
        subprocess.run(["git", "reset", "-q", "--hard", self.stack], cwd=self.root, capture_output=True)

    # ------------------------------------------------------------ 历史 / 检索

    def log(self, ref: str, path: str | None = None, limit: int = 50) -> list[Revision]:
        fmt = "%H%x1f%an%x1f%aI%x1f%s%x1f%b%x1e"
        args = ["git", "log", f"--max-count={limit}", f"--format={fmt}"]
        if ref == self.stack:
            args.append("--first-parent")            # stack 的时间线:每个 merge 节点就是那次层提交
        args.append(ref)
        if path:
            args += ["--", path]
        out = subprocess.run(args, cwd=self.root, capture_output=True, text=True).stdout
        revs = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, author, date, subject, body = (rec.split("\x1f") + [""] * 5)[:5]
            revs.append(Revision(sha=sha, author=author, date=date, subject=subject, body=body.strip()))
        return revs

    def grep(self, query: str) -> list[GrepHit]:
        out = subprocess.run(["git", "grep", "-n", "-i", "-I", "--", query, self.stack],
                             cwd=self.root, capture_output=True, text=True).stdout
        hits = []
        for line in out.splitlines():
            try:
                _, path, lineno, text = line.split(":", 3)      # <ref>:<path>:<line>:<text>
            except ValueError:
                continue
            hits.append(GrepHit(path, int(lineno), text))
        return hits
