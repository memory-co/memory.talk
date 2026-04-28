"""LocalStorage — write_text / read_text basic contract."""
from __future__ import annotations
from pathlib import Path

from memorytalk.provider.storage import LocalStorage


async def test_write_then_read_roundtrip(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("foo/bar.txt", "hello world")
    assert await s.read_text("foo/bar.txt") == "hello world"


async def test_read_missing_returns_none(tmp_path: Path):
    s = LocalStorage(tmp_path)
    assert await s.read_text("nope/nada.txt") is None


async def test_write_creates_parent_dirs(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("a/b/c/d/file.json", '{"k": 1}')
    assert (tmp_path / "a" / "b" / "c" / "d" / "file.json").exists()


async def test_write_overwrites_existing(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("once.txt", "v1")
    await s.write_text("once.txt", "v2")
    assert await s.read_text("once.txt") == "v2"
