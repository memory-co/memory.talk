"""CLI: setup — interactive idempotent install / configure / restart.

Walkthrough lives in ``docs/cli/v2/setup.md``. This module is the entry
point that:

1. Decides which Python env the wizard runs in:
   - already running from ``~/.memory-talk/.venv`` → continue here
   - otherwise → ask once whether to bootstrap that dedicated venv
     (default yes; answering no keeps the current env)
2. If the user opted in: bootstraps the venv, then re-execs into it.
3. **Runs the PATH takeover** so every ``memory-talk`` on the user's
   ``$PATH`` redirects to the chosen target. This happens *before* the
   wizard because PATH state is independent of settings — putting it
   inside the wizard tied it to "settings changed", which was wrong.
4. Drives the configuration wizard in the chosen env.

Upgrades are not handled here — there will be a separate command for
that (``memory-talk upgrade`` or similar).

`--data-root` is intentionally absent — setup is the bootstrap step, it
needs to anchor on a known location. data_root for *other* commands
remains overridable via the ``MEMORY_TALK_DATA_ROOT`` env var; setup
honors it for where ``settings.json`` lands.

Submodules:
- ``helpers``   — pure settings.json + symlink helpers (no rich, no click)
- ``venv``      — venv path resolution + bootstrap + re-exec + current-env helper
- ``steps/``    — one module per wizard step
- ``wizard``    — composes the steps in order
- ``summary``   — final Markdown table emitted on stdout

The shared rich Console + questionary prompts live in
``memorytalk.cli.console`` (sibling package), shared with any other CLI
subcommand that wants the same look and feel.

The venv helpers are re-imported here so tests can monkeypatch them on
the package itself (``setup_module._already_in_venv = ...``).
"""
from __future__ import annotations
import subprocess
import sys

import click

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md, emit_md_err
from memorytalk.config import Config

from memorytalk.cli import console
from memorytalk.cli.console import err_console

from .helpers import read_settings_raw
from .steps.path_takeover import _step_path_takeover
from .summary import _summary_md
from .venv import (
    _already_in_venv, _bootstrap_venv, _data_root, _reexec_into_venv,
    _venv_root, current_memory_talk_bin,
)
from .wizard import _wizard


_BOOTSTRAP_OPTIONS = [
    console.Option(
        "yes",
        description="install memorytalk into a managed venv (recommended — isolates from system Python)",
    ),
    console.Option(
        "no",
        description="keep using the current python env (you manage your own setup)",
    ),
]


@click.command("setup")
def setup() -> None:
    """Interactive wizard: install / reconfigure / restart memory-talk."""
    # 1. Decide whether to bootstrap the dedicated venv.
    #    - If we're already inside it → no prompt, just continue.
    #    - Otherwise → ask once. Answering yes triggers bootstrap+execv;
    #      after execv the new process re-enters this function with
    #      `_already_in_venv()` returning True and skips the prompt.
    if not _already_in_venv():
        choice = console.select(
            f"Bootstrap a dedicated venv at {_venv_root()}?",
            _BOOTSTRAP_OPTIONS, default="yes",
        )
        if choice == "yes":
            try:
                _bootstrap_venv()
            except subprocess.CalledProcessError as e:
                emit_md_err(fmt_error(
                    f"failed to bootstrap venv: {e}\n"
                    "  check network connectivity and that pip can reach PyPI."
                ))
                sys.exit(1)
            _reexec_into_venv()
            return  # not reached on success

    # 2. Resolve which `memory-talk` script we're actually running, so the
    #    PATH takeover + summary point at the right binary.
    memory_talk_bin = current_memory_talk_bin()

    # 3. PATH takeover — make every memory-talk on $PATH point at the
    #    chosen target. Independent of settings, runs every setup
    #    invocation. The function is idempotent: silent + no prompt when
    #    everything's already correct.
    takeover_result = _step_path_takeover(memory_talk_bin)

    # 4. Refuse to run against a v1 data root.
    cfg = Config(_data_root())
    try:
        cfg.validate()
    except Exception as e:
        emit_md_err(fmt_error(str(e)))
        sys.exit(1)

    try:
        old_raw = read_settings_raw(cfg.settings_path)
    except ValueError:
        if not console.confirm(
            "settings.json is corrupted. Back it up to settings.json.bak and re-initialize?",
            default=True,
        ):
            sys.exit(1)
        bak = cfg.settings_path.with_suffix(".json.bak")
        cfg.settings_path.replace(bak)
        old_raw = None
        err_console.print(f"[dim]backed up corrupt settings → {bak}[/dim]")

    is_first_install = old_raw is None
    cfg.data_root.mkdir(parents=True, exist_ok=True)

    try:
        result = _wizard(cfg, old_raw, is_first_install, memory_talk_bin=memory_talk_bin)
    except KeyboardInterrupt:
        # PATH takeover already ran above and may have committed; only
        # the wizard's settings write is being skipped.
        err_console.print(
            "\n[dim]aborted by user — settings.json not written "
            "(any PATH takeover above is already committed)[/dim]"
        )
        sys.exit(130)

    # Summary reads `path_takeover` from the result dict; takeover ran
    # upstream of the wizard, so we inject it here.
    result["path_takeover"] = takeover_result

    emit_md(_summary_md(cfg, result, memory_talk_bin=memory_talk_bin))
