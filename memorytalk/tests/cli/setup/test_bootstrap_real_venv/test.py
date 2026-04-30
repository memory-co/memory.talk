"""Real-subprocess test for the venv bootstrap path.

Spins up two venvs:

  venv_a   = the "outer" caller (some other Python where memorytalk got
             pip-installed by a user)
  venv_b   = the dedicated venv at HOME/.memory-talk/.venv that setup
             auto-creates when it detects it isn't running from venv_b

Verifies that running ``<venv_a>/bin/memory-talk setup`` triggers the
bootstrap+execv path and produces a working venv_b. Does NOT verify
the wizard end-to-end (that's covered in-process by the other setup
scenarios).
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[5]


pytestmark = pytest.mark.skipif(
    shutil.which("python3") is None,
    reason="needs python3 on PATH for venv creation",
)


def _make_venv(at: Path) -> None:
    subprocess.run([sys.executable, "-m", "venv", str(at)], check=True)


def _pip_install(venv: Path, *args: str) -> None:
    subprocess.run([str(venv / "bin" / "pip"), "install", *args],
                   check=True, capture_output=True)


def test_setup_bootstraps_inner_venv_via_real_subprocess(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    venv_a = tmp_path / "venv_a"

    # 1. outer venv + memorytalk installed from the local repo
    _make_venv(venv_a)
    _pip_install(venv_a, str(REPO_ROOT))

    # 2. run `memory-talk setup` from venv_a with HOME redirected and the
    #    bootstrap source overridden to the same local repo (so the inner
    #    venv install doesn't hit PyPI).
    env = {
        **os.environ,
        "HOME": str(fake_home),
        "MEMORYTALK_BOOTSTRAP_SOURCE": str(REPO_ROOT),
        # --no-deps keeps the inner-venv install tiny (just the entry
        # point script). Bootstrap orchestration is what we verify here;
        # the inner script's runtime imports failing afterwards is fine
        # — we only check that files exist on disk.
        "MEMORYTALK_BOOTSTRAP_PIP_ARGS": "--no-deps",
    }
    proc = subprocess.run(
        [str(venv_a / "bin" / "memory-talk"), "setup"],
        input="",  # EOF on first wizard prompt — we don't care about wizard outcome
        env=env,
        capture_output=True, text=True,
        timeout=180,
    )

    # 3. After execv, the inner setup runs the wizard, blocks on the
    #    first prompt with no input, and exits non-zero. That's fine —
    #    we only need the venv to exist.
    target_venv = fake_home / ".memory-talk" / ".venv"
    assert (target_venv / "bin" / "python").exists(), (
        f"inner venv was not created. stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert (target_venv / "bin" / "memory-talk").exists(), (
        f"memory-talk binary missing inside inner venv. stderr={proc.stderr!r}"
    )
