"""文件系统型 provider:按路径存字节。LocalFS 是默认实现;OSS / S3 照同一个基类。"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stat:
    size: int
    mtime: float


class FileSystemProvider:
    family = "fs"

    def read(self, path: str) -> bytes | None: raise NotImplementedError
    def write(self, path: str, data: bytes) -> None: raise NotImplementedError      # 整体替换,对调用方原子
    def append(self, path: str, data: bytes) -> None: raise NotImplementedError     # 追加到末尾
    def delete(self, path: str) -> None: raise NotImplementedError
    def exists(self, path: str) -> bool: raise NotImplementedError
    def list(self, prefix: str) -> list[str]: raise NotImplementedError             # 前缀下全部路径(相对根)
    def stat(self, path: str) -> Stat | None: raise NotImplementedError

    # 能力:不是每个实现都有
    def local_path(self, path: str) -> Path | None:
        return None

    def has(self, capability: str) -> bool:
        return capability in getattr(self, "capabilities", ())


class LocalFS(FileSystemProvider):
    """本地文件系统:临时文件 + rename 的原子写、O_APPEND 追加、单写者、无缓存直读。"""
    capabilities = ("local_path",)

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, path: str) -> Path:
        p = (self.root / path.strip("/")).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError(f"路径越界:{path}")
        return p

    def read(self, path: str) -> bytes | None:
        try:
            return self._p(path).read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            return None

    def write(self, path: str, data: bytes) -> None:
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=p.suffix)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def append(self, path: str, data: bytes) -> None:
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "ab") as f:
            f.write(data)

    def delete(self, path: str) -> None:
        try:
            self._p(path).unlink()
        except FileNotFoundError:
            pass

    def exists(self, path: str) -> bool:
        return self._p(path).is_file()

    def list(self, prefix: str) -> list[str]:
        base = self._p(prefix) if prefix else self.root
        if not base.is_dir():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())

    def stat(self, path: str) -> Stat | None:
        try:
            st = self._p(path).stat()
        except FileNotFoundError:
            return None
        return Stat(size=st.st_size, mtime=st.st_mtime)

    def local_path(self, path: str) -> Path | None:
        return self._p(path)
