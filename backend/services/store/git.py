"""git 仓库封装:一个决定一个 commit;log 是历史;grep 是检索(store.md §2、§5)。

只用 git 命令行,不引第三方库。单进程内用锁串行化提交。
"""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str
    date: str
    subject: str
    body: str


@dataclass(frozen=True)
class GrepHit:
    path: str
    line: int
    text: str


class GitRepo:
    def __init__(self, root: Path, author_name: str, author_email: str) -> None:
        self.root = root
        self._author = ["-c", f"user.name={author_name}", "-c", f"user.email={author_email}",
                        "-c", "core.quotepath=false"]
        self._lock = threading.Lock()

    # ---- 基础 ----

    def _run(self, *args: str, check: bool = True) -> str:
        proc = subprocess.run(
            ["git", *self._author, *args],
            cwd=self.root, capture_output=True, text=True,
        )
        if check and proc.returncode != 0:
            raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
        return proc.stdout

    def ensure(self) -> None:
        """有则用,无则 init。幂等。"""
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._run("init", "-q", "-b", "main")
            (self.root / "cards").mkdir(exist_ok=True)
            (self.root / "issues").mkdir(exist_ok=True)
            (self.root / "README.md").write_text(
                "# memory\n\nmemory.talk v5 的认知层:`cards/` 是词条,`issues/` 是讨论页。"
                "每个 commit 是一个决定。\n", encoding="utf-8")
            self._run("add", "-A")
            self._run("commit", "-q", "-m", "init memory")

    # ---- 提交 ----

    def commit(self, paths: list[str], subject: str, body: str = "") -> str:
        """把这些路径的当前状态作为一个决定提交。返回 sha。"""
        with self._lock:
            self._run("add", "-A", "--", *paths)
            msg = subject if not body else f"{subject}\n\n{body}"
            self._run("commit", "-q", "--allow-empty", "-m", msg, "--", *paths)
            return self._run("rev-parse", "HEAD").strip()

    # ---- 历史 ----

    def log(self, path: str | None = None, limit: int = 50) -> list[Commit]:
        fmt = "%H%x1f%an%x1f%aI%x1f%s%x1f%b%x1e"
        args = ["log", f"--max-count={limit}", f"--format={fmt}"]
        if path:
            args += ["--", path]
        out = self._run(*args, check=False)
        commits: list[Commit] = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, author, date, subject, body = (rec.split("\x1f") + [""] * 5)[:5]
            commits.append(Commit(sha, author, date, subject, body.strip()))
        return commits

    def show(self, sha: str, path: str) -> str | None:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=false", "show", f"{sha}:{path}"], cwd=self.root, capture_output=True, text=True)
        return out.stdout if out.returncode == 0 else None

    # ---- 检索 ----

    def grep(self, query: str, pathspec: str | None = None) -> list[GrepHit]:
        args = ["grep", "-n", "-i", "-I", "--", query]
        if pathspec:
            args.append(pathspec)
        out = self._run(*args, check=False)
        hits: list[GrepHit] = []
        for line in out.splitlines():
            try:
                path, lineno, text = line.split(":", 2)
            except ValueError:
                continue
            hits.append(GrepHit(path, int(lineno), text))
        return hits
