"""manual / resume command-construction is testable in isolation.

We don't actually exec claude (would replace the test process). Instead
we test the pure ``_resolve_exec_args`` helper. The exec wiring itself
is a thin wrapper around os.execvp with no logic worth testing.
"""
from __future__ import annotations
from pathlib import Path

from memorytalk.cli.explore import _resolve_exec_args


def test_manual_yields_bare_claude(tmp_path: Path):
    cwd, argv = _resolve_exec_args(tmp_path, None)
    assert cwd == tmp_path
    assert argv == ["claude"]


def test_resume_with_raw_uuid(tmp_path: Path):
    cwd, argv = _resolve_exec_args(tmp_path, "abc-123")
    assert cwd == tmp_path
    assert argv == ["claude", "--resume", "abc-123"]


def test_resume_strips_sess_prefix(tmp_path: Path):
    cwd, argv = _resolve_exec_args(tmp_path, "sess_abc-123")
    assert argv == ["claude", "--resume", "abc-123"]
