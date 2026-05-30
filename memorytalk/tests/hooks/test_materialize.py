"""Hash + copy helpers underpinning the idempotent install step."""
from __future__ import annotations

import json
from pathlib import Path

from memorytalk.hooks import materialize


def test_dir_hash_stable_across_calls(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.json").write_text('{"v": 1}\n')
    (tmp_path / "b.json").write_text('{"v": 2}\n')

    h1 = materialize.dir_hash(tmp_path)
    h2 = materialize.dir_hash(tmp_path)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_dir_hash_ignores_non_json(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text('{"v": 1}\n')
    h_before = materialize.dir_hash(tmp_path)
    (tmp_path / "README.txt").write_text("noise\n")
    (tmp_path / "x.pyc").write_text("noise\n")
    assert materialize.dir_hash(tmp_path) == h_before


def test_dir_hash_changes_with_content(tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text('{"v": 1}\n')
    h1 = materialize.dir_hash(tmp_path)
    f.write_text('{"v": 2}\n')
    h2 = materialize.dir_hash(tmp_path)
    assert h1 != h2


def test_dir_hash_missing_dir_is_empty_string(tmp_path: Path) -> None:
    assert materialize.dir_hash(tmp_path / "nope") == ""


def test_materialize_real_assets_round_trip(tmp_path: Path) -> None:
    """The wheel-shipped assets must hash non-empty and survive a copy."""
    for sub in ("claude_code", "codex"):
        src_hash = materialize.bundled_hash(sub)
        assert src_hash, f"bundled_hash({sub!r}) returned empty"
        dst = tmp_path / sub
        materialize.materialize(sub, dst)
        assert materialize.dir_hash(dst) == src_hash
        # Re-copy is a no-op
        assert materialize.materialize(sub, dst) is False
