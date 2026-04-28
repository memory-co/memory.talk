"""LocalStorage — append_text contract for jsonl-style accumulation."""
from __future__ import annotations
from pathlib import Path

from memory_talk_v2.provider.storage import LocalStorage


async def test_append_to_new_creates_file(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.append_text("log.jsonl", '{"a":1}\n')
    assert await s.read_text("log.jsonl") == '{"a":1}\n'


async def test_append_accumulates(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.append_text("log.jsonl", '{"a":1}\n')
    await s.append_text("log.jsonl", '{"a":2}\n')
    await s.append_text("log.jsonl", '{"a":3}\n')
    assert await s.read_text("log.jsonl") == '{"a":1}\n{"a":2}\n{"a":3}\n'


async def test_append_creates_parent_dirs(tmp_path: Path):
    s = LocalStorage(tmp_path)
    await s.append_text("nested/deep/log.jsonl", "first\n")
    assert (tmp_path / "nested" / "deep" / "log.jsonl").exists()


async def test_append_then_read_roundtrip(tmp_path: Path):
    s = LocalStorage(tmp_path)
    for i in range(5):
        await s.append_text("events.jsonl", f"line-{i}\n")
    assert await s.read_text("events.jsonl") == "line-0\nline-1\nline-2\nline-3\nline-4\n"
