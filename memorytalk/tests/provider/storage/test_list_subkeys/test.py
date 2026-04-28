"""LocalStorage — list_subkeys recursive listing primitive."""
from __future__ import annotations
from pathlib import Path

from memorytalk.provider.storage import LocalStorage


async def test_list_empty_prefix_returns_empty(tmp_path: Path):
    s = LocalStorage(tmp_path)
    assert await s.list_subkeys("nope") == []


async def test_list_returns_relative_keys(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("zone/a.txt", "1")
    await s.write_text("zone/b.txt", "2")
    keys = await s.list_subkeys("zone")
    # forward-slash relative keys, no absolute path noise
    assert all(not k.startswith("/") for k in keys)
    assert "zone/a.txt" in keys and "zone/b.txt" in keys


async def test_list_is_recursive(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("root/x/1.json", "x")
    await s.write_text("root/y/2.json", "y")
    await s.write_text("root/y/sub/3.json", "z")
    keys = await s.list_subkeys("root")
    assert keys == ["root/x/1.json", "root/y/2.json", "root/y/sub/3.json"]


async def test_list_skips_directories(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.write_text("a/b/c/leaf.txt", "1")
    keys = await s.list_subkeys("a")
    # Intermediate dirs ("a/b", "a/b/c") are not file keys — only leaf.
    assert keys == ["a/b/c/leaf.txt"]


async def test_list_is_sorted(tmp_path: Path):
    s = LocalStorage(tmp_path)
    # Write in non-alphabetical order
    await s.write_text("p/zeta.txt", "")
    await s.write_text("p/alpha.txt", "")
    await s.write_text("p/mu.txt", "")
    keys = await s.list_subkeys("p")
    assert keys == sorted(keys)
    assert keys == ["p/alpha.txt", "p/mu.txt", "p/zeta.txt"]
