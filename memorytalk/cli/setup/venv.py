"""Venv path helpers + bootstrap + re-exec.

The setup command's standard mode forces the wizard to run from inside
``~/.memory-talk/.venv``. This module owns:

- where that venv lives (``_venv_root`` and friends)
- whether we're already inside it (``_already_in_venv``)
- creating it / installing memorytalk into it (``_bootstrap_venv``)
- swapping the running process to its python (``_reexec_into_venv``)

Everything else in the package can assume the venv exists and we're
running from it.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md_err

from ._io import err_console


def _venv_root() -> Path:
    """The dedicated memorytalk venv. Always at ~/.memory-talk/.venv,
    independent of MEMORY_TALK_DATA_ROOT (data + venv are decoupled)."""
    return Path.home() / ".memory-talk" / ".venv"


def _venv_python() -> Path:
    return _venv_root() / "bin" / "python"


def _venv_memory_talk() -> Path:
    return _venv_root() / "bin" / "memory-talk"


def _data_root() -> Path:
    """Where settings.json + sessions/cards/links/etc live. Honors
    MEMORY_TALK_DATA_ROOT env var; defaults to ~/.memory-talk."""
    env = os.environ.get("MEMORY_TALK_DATA_ROOT")
    return Path(env) if env else Path.home() / ".memory-talk"


def _already_in_venv() -> bool:
    """True iff the running interpreter is the dedicated venv's python."""
    try:
        return Path(sys.executable).resolve() == _venv_python().resolve()
    except OSError:
        return False


def _bootstrap_venv() -> None:
    """Make sure ~/.memory-talk/.venv exists and has memorytalk installed.

    - First call (venv missing): creates it, then pip install memorytalk.
    - Steady-state (venv present + memory-talk installed): no-op.

    Upgrades are intentionally NOT handled here — there will be a
    separate command for that.

    Source of memorytalk is PyPI by default. For tests / dev workflows
    that want to install from a local checkout instead, set the
    ``MEMORYTALK_BOOTSTRAP_SOURCE`` env var to a path or VCS URL — that
    value is passed verbatim to ``pip install``.
    """
    venv = _venv_root()
    py = _venv_python()
    pip = venv / "bin" / "pip"

    if not py.exists():
        err_console.print(f"[dim]bootstrapping venv at {venv} ...[/dim]")
        venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)

    if not _venv_memory_talk().exists():
        source = os.environ.get("MEMORYTALK_BOOTSTRAP_SOURCE", "memorytalk")
        extra = os.environ.get("MEMORYTALK_BOOTSTRAP_PIP_ARGS", "").split()
        cmd = [str(pip), "install", *extra, source]
        err_console.print(f"[dim]installing {source} into {venv} ...[/dim]")
        subprocess.run(cmd, check=True)


def current_memory_talk_bin() -> Path:
    """Path to the ``memory-talk`` script of the env we're running from now.

    After a successful bootstrap+execv this equals ``_venv_memory_talk()``.
    If the user opted out of the dedicated venv, it points at whichever env
    they invoked ``memory-talk`` from. Used by the alias step + summary so
    those reflect reality instead of always assuming ``~/.memory-talk/.venv``.
    """
    return Path(sys.executable).parent / "memory-talk"


def _reexec_into_venv() -> None:
    """Replace the current process with ``<venv>/bin/memory-talk <argv...>``.

    Intentionally does NOT return — on success the OS swaps the process
    image. On failure (rare: missing binary, permission, etc.) we surface
    a clean error and exit 1 instead of silently continuing in the wrong
    Python.
    """
    target = _venv_memory_talk()
    if not target.exists():
        emit_md_err(fmt_error(
            f"venv binary missing after bootstrap: {target} — install seems "
            "to have failed silently. Re-run setup; the missing binary will "
            "trigger another install attempt."
        ))
        sys.exit(1)
    try:
        os.execv(str(target), [str(target), *sys.argv[1:]])
    except OSError as e:
        emit_md_err(fmt_error(f"failed to re-exec into venv: {e}"))
        sys.exit(1)
