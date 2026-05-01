"""Direct tests for ``_step_path_takeover`` — classify and redirect.

The wizard tests stub this step out (PATH state is nasty to fake at the
whole-CLI level). Here we drive the function directly with a synthetic
``$PATH`` that points at fake bin dirs in tmp_path, exercising every
branch of the classification table.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def takeover_env(tmp_path, monkeypatch):
    """Build a synthetic $PATH and patch the prompt shim.

    Layout: tmp_path/{bin_real, bin_symlink, bin_target, ...} — each is
    a directory that may contain a ``memory-talk`` file/symlink. The
    fixture sets ``$PATH`` to the listed dirs and yields helpers.
    """
    target_dir = tmp_path / "bin_target"
    target_dir.mkdir()
    target = target_dir / "memory-talk"
    target.write_text("#!/usr/bin/env python3\n")  # the canonical script
    target.chmod(0o755)

    bin_real = tmp_path / "bin_real"
    bin_real.mkdir()
    bin_symlink = tmp_path / "bin_symlink"
    bin_symlink.mkdir()

    # PATH contains the target's dir plus bin_real and bin_symlink.
    new_path = os.pathsep.join([str(bin_real), str(bin_symlink), str(target_dir)])
    monkeypatch.setenv("PATH", new_path)

    # Patch the prompt shim used by path_takeover: yes by default unless
    # a test overrides ``confirm_answer``.
    from memorytalk.util import console
    state = {"confirm_answer": True}
    monkeypatch.setattr(console, "confirm", lambda *a, **kw: state["confirm_answer"])

    class Env:
        pass

    env = Env()
    env.tmp_path = tmp_path
    env.target = target
    env.bin_real = bin_real
    env.bin_symlink = bin_symlink
    env.state = state
    return env


def test_takeover_replaces_regular_file_and_redirects_symlink(takeover_env):
    from memorytalk.cli.setup.steps.path_takeover import _step_path_takeover

    real = takeover_env.bin_real / "memory-talk"
    real.write_text("#!/opt/homebrew/.../python3.12\n# pip-installed entry-point\n")
    real.chmod(0o755)

    sym = takeover_env.bin_symlink / "memory-talk"
    other_target = takeover_env.tmp_path / "bin_target" / "old_thing"
    other_target.write_text("old\n")
    sym.symlink_to(other_target)

    result = _step_path_takeover(takeover_env.target)

    statuses = {a["path"]: a["status"] for a in result["actions"]}
    assert statuses[str(real)] == "replaced"
    assert statuses[str(sym)] == "redirected"
    # The target's own location was already correct.
    assert statuses[str(takeover_env.target)] == "ok"

    # Backup created for the regular file
    bak = Path(str(real) + ".bak")
    assert bak.exists()
    assert bak.read_text().startswith("#!/opt/homebrew/")

    # Both replacements are now symlinks pointing at target
    assert real.is_symlink()
    assert real.resolve() == takeover_env.target.resolve()
    assert sym.is_symlink()
    assert sym.resolve() == takeover_env.target.resolve()


def test_takeover_skipped_when_user_declines(takeover_env):
    from memorytalk.cli.setup.steps.path_takeover import _step_path_takeover

    real = takeover_env.bin_real / "memory-talk"
    real.write_text("# brew script\n")
    real.chmod(0o755)
    original_text = real.read_text()

    takeover_env.state["confirm_answer"] = False
    result = _step_path_takeover(takeover_env.target)

    statuses = {a["path"]: a["status"] for a in result["actions"]}
    assert statuses[str(real)] == "skipped"

    # Original file untouched
    assert not real.is_symlink()
    assert real.read_text() == original_text
    assert not Path(str(real) + ".bak").exists()


def test_takeover_no_op_when_already_pointing_at_target(takeover_env):
    from memorytalk.cli.setup.steps.path_takeover import _step_path_takeover

    sym = takeover_env.bin_symlink / "memory-talk"
    sym.symlink_to(takeover_env.target)

    result = _step_path_takeover(takeover_env.target)

    statuses = {a["path"]: a["status"] for a in result["actions"]}
    assert statuses[str(sym)] == "ok"
    assert statuses[str(takeover_env.target)] == "ok"
    # No "redirected" or "replaced" actions — pure noop
    assert all(a["status"] == "ok" for a in result["actions"])


def test_takeover_not_found_when_path_is_empty(takeover_env, monkeypatch):
    from memorytalk.cli.setup.steps.path_takeover import _step_path_takeover

    monkeypatch.setenv("PATH", str(takeover_env.tmp_path / "nonexistent"))

    result = _step_path_takeover(takeover_env.target)

    assert len(result["actions"]) == 1
    assert result["actions"][0]["status"] == "not_found"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only behavior")
def test_takeover_handles_no_perm_on_file(takeover_env):
    """When mv to .bak fails (parent dir read-only), the action reports no_perm."""
    from memorytalk.cli.setup.steps.path_takeover import _step_path_takeover

    real = takeover_env.bin_real / "memory-talk"
    real.write_text("# brew script\n")
    real.chmod(0o755)

    # Make the parent dir read-only so rename fails.
    takeover_env.bin_real.chmod(0o555)
    try:
        result = _step_path_takeover(takeover_env.target)
    finally:
        takeover_env.bin_real.chmod(0o755)  # restore for cleanup

    statuses = {a["path"]: a["status"] for a in result["actions"]}
    assert statuses[str(real)] == "no_perm"
    # File preserved (not even moved to .bak)
    assert real.exists()
    assert not real.is_symlink()
