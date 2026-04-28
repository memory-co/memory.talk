"""LocalStorage — exists / delete head + delete primitives."""
from __future__ import annotations
from pathlib import Path

from memorytalk.provider.storage import LocalStorage


async def test_exists_after_write(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("a/b.txt", "x")
    assert await s.exists("a/b.txt") is True


async def test_exists_for_missing_is_false(tmp_path: Path):
    s = LocalStorage(tmp_path)
    assert await s.exists("never/written.txt") is False


async def test_delete_removes_key(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("doomed.txt", "bye")
    await s.delete("doomed.txt")
    assert await s.exists("doomed.txt") is False
    assert await s.read_text("doomed.txt") is None


async def test_delete_missing_is_noop(tmp_path: Path):
    s = LocalStorage(tmp_path)
    # Must not raise — retention loops rely on this idempotency.
    await s.delete("never/existed.txt")
