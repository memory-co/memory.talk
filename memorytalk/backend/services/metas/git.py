"""git 原语:只跟 git 命令行说话,不认识层。Repo(repo.py)在它上面搭分层拓扑。

全部 plumbing:hash-object / update-index / write-tree / commit-tree / update-ref;读走 ls-tree / show;历史走 log;检索走 grep。
不碰工作树(只在需要人 ls / cat 时 reset 让它跟上某个 ref)。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from memorytalk.backend.models.metas import Revision


@dataclass(frozen=True)
class Entry:
    mode: str
    oid: str
    path: str


@dataclass(frozen=True)
class GrepHit:
    file: str
    line: int
    text: str


class Git:
    def __init__(self, root: Path, author_name: str, author_email: str, initial_branch: str = "main") -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            self.text("init", "-q", "-b", initial_branch)
        for k, v in (("user.name", author_name), ("user.email", author_email), ("core.quotepath", "false")):
            self.text("config", k, v)

    # ---- 调用 ----

    def run(self, *args: str, stdin: bytes | None = None, check: bool = True, env: dict | None = None) -> bytes:
        p = subprocess.run(["git", *args], cwd=self.root, input=stdin, capture_output=True, env={**os.environ, **(env or {})})
        if check and p.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {p.stderr.decode(errors='replace').strip()}")
        return p.stdout

    def text(self, *args: str, **kw) -> str:
        return self.run(*args, **kw).decode("utf-8", "replace")

    # ---- 对象 / 树 / 提交 / ref ----

    def resolve(self, ref: str) -> str | None:
        p = subprocess.run(["git", "rev-parse", "--verify", "-q", ref], cwd=self.root, capture_output=True, text=True)
        return p.stdout.strip() or None

    def ls_tree(self, rev: str, prefix: str = "") -> list[Entry]:
        out = self.run("ls-tree", "-r", "-z", rev, *(["--", prefix] if prefix else []), check=False)
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

    def tree_of(self, commit: str) -> str:
        return self.text("rev-parse", f"{commit}^{{tree}}").strip()

    def hash_object(self, data: bytes) -> str:
        return self.text("hash-object", "-w", "--stdin", stdin=data).strip()

    def write_tree(self, entries: dict[str, Entry]) -> str:
        """一组 entry → 一棵树(走临时 index,不碰真 index)。"""
        fd, idx = tempfile.mkstemp(prefix="mt-index-", dir=self.root / ".git")
        os.close(fd)
        os.unlink(idx)
        payload = b"".join(f"{e.mode} blob {e.oid}\t{e.path}".encode("utf-8", "surrogateescape") + b"\0" for e in entries.values())
        try:
            self.run("update-index", "-z", "--index-info", stdin=payload, env={"GIT_INDEX_FILE": idx})
            return self.text("write-tree", env={"GIT_INDEX_FILE": idx}).strip()
        finally:
            try:
                os.unlink(idx)
            except FileNotFoundError:
                pass

    def commit_tree(self, tree: str, parents: list[str], message: str, author: tuple[str, str] | None = None) -> str:
        """author = (名字, 邮箱);没有则用仓库配置的默认名。"""
        args = ["commit-tree", tree]
        for p in parents:
            args += ["-p", p]
        env = {"GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1]} if author else None
        return self.text(*args, stdin=message.encode(), env=env).strip()

    def update_ref(self, ref: str, new: str, old: str | None = None) -> None:
        self.text("update-ref", ref, new, *([old] if old else []))

    def set_head(self, ref: str) -> None:
        self.text("symbolic-ref", "HEAD", ref)

    def root_commits(self, ref: str) -> list[str]:
        return self.text("rev-list", "--max-parents=0", ref, check=False).split()

    def sync_worktree(self, ref: str) -> None:
        """工作树跟上 ref(只为了人能 ls / cat;服务从不读它)。"""
        subprocess.run(["git", "reset", "-q", "--hard", ref], cwd=self.root, capture_output=True)

    # ---- 读 / 历史 / 检索 ----

    def show(self, rev: str, path: str) -> bytes | None:
        p = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=self.root, capture_output=True)
        return p.stdout if p.returncode == 0 else None

    def log(self, ref: str, path: str | None = None, limit: int = 50, first_parent: bool = False) -> list[Revision]:
        fmt = "%H%x1f%an%x1f%aI%x1f%s%x1f%b%x1e"
        args = ["git", "log", f"--max-count={limit}", f"--format={fmt}"] + (["--first-parent"] if first_parent else []) + [ref]
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

    def log_files(self, ref: str, path: str | None = None, limit: int = 50, first_parent: bool = False) -> list[tuple[Revision, list[str]]]:
        """log + 每次提交碰了哪些文件(--name-only)。merge 节点用 --first-parent 时,文件是相对第一个父的差异。"""
        fmt = "%x1e%H%x1f%an%x1f%aI%x1f%s"
        args = ["git", "log", f"--max-count={limit}", f"--format={fmt}", "--name-only"] + (["--first-parent", "-m"] if first_parent else []) + [ref]
        if path:
            args += ["--", path]
        out = subprocess.run(args, cwd=self.root, capture_output=True, text=True).stdout
        revs: list[tuple[Revision, list[str]]] = []
        for rec in out.split("\x1e"):
            if not rec.strip():
                continue
            head, _, rest = rec.partition("\n")
            sha, author, date, subject = (head.split("\x1f") + [""] * 4)[:4]
            files = [l.strip() for l in rest.splitlines() if l.strip()]
            revs.append((Revision(sha=sha, author=author, date=date, subject=subject), files))
        return revs

    def grep(self, query: str, ref: str) -> list[GrepHit]:
        out = subprocess.run(["git", "grep", "-n", "-i", "-I", "--", query, ref], cwd=self.root, capture_output=True, text=True).stdout
        hits = []
        for line in out.splitlines():
            try:
                _, path, lineno, text = line.split(":", 3)      # <ref>:<path>:<line>:<text>
            except ValueError:
                continue
            hits.append(GrepHit(path, int(lineno), text))
        return hits
