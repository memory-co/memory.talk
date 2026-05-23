"""CLI: upgrade — pull the latest release from PyPI.

Why a dedicated subcommand instead of just telling users to run
``pip install -U memorytalk``:

- **The pip in $PATH may not be the right one.** A user might have
  multiple Python installs, a venv, pipx, conda, etc. ``pip install -U``
  from a random shell could land memorytalk in a different site-packages
  than the one we're currently executing from — net effect "upgrade ran
  but the CLI is still old". We invoke pip via ``sys.executable -m pip``
  so the upgrade always targets THIS interpreter's site-packages.
- **Confirmation + version diff before any install.** Users see ``current
  → latest`` and explicitly say yes. ``--yes`` for scripted upgrades.
- **Post-install verification.** pip exit 0 doesn't always mean the new
  version actually landed (cache weirdness, partial installs). We re-
  query the installed version in a fresh subprocess to confirm.

Out of scope (do via ``pip`` directly if needed): ``--pre`` flag,
pinning to a specific version, custom index URL, rollback.
"""
from __future__ import annotations
import importlib.metadata
import json
import subprocess
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

import click

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md, emit_md_err

PACKAGE = "memorytalk"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE}/json"
_FETCH_TIMEOUT = 10.0


@click.command("upgrade")
@click.option(
    "--yes", "-y", "auto_yes", is_flag=True, default=False,
    help="Skip the confirmation prompt — for scripted upgrades.",
)
@click.option(
    "--check", "check_only", is_flag=True, default=False,
    help="Only print current and latest versions; don't install.",
)
def upgrade(auto_yes: bool, check_only: bool) -> None:
    """Upgrade memorytalk to the latest PyPI release."""
    current = _current_version()
    if current is None:
        emit_md_err(fmt_error(
            f"{PACKAGE} is not installed in this Python environment "
            f"({sys.executable}). This shouldn't happen — please reinstall."
        ))
        sys.exit(1)

    latest = _fetch_latest_pypi_version()
    if latest is None:
        emit_md_err(fmt_error(
            "Could not reach PyPI to check the latest version. "
            f"Check your network and retry, or run `{sys.executable} -m "
            f"pip install --upgrade {PACKAGE}` directly."
        ))
        sys.exit(1)

    lines = [
        "# upgrade",
        "",
        f"- package: `{PACKAGE}`",
        f"- current: `{current}`",
        f"- latest:  `{latest}`",
        f"- python:  `{sys.executable}`",
        "",
    ]

    if current.strip() == latest.strip():
        lines.append("Already on the latest version. Nothing to do.")
        emit_md("\n".join(lines) + "\n")
        return

    lines.append(f"**Available**: `{current}` → `{latest}`")
    if check_only:
        lines.append("")
        lines.append("`--check` mode — not installing. Run without `--check` to upgrade.")
        emit_md("\n".join(lines) + "\n")
        return

    emit_md("\n".join(lines) + "\n")

    if not auto_yes and not click.confirm(
        f"\nUpgrade to {latest}?", default=False,
    ):
        click.echo("Cancelled.")
        return

    # Use ``sys.executable -m pip`` so the upgrade hits the pip belonging
    # to THIS interpreter — not whatever ``pip`` resolves to on $PATH
    # (could be a different venv / system Python).
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE]
    click.echo(f"\n$ {' '.join(cmd)}\n")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        emit_md_err(fmt_error(f"pip exited with code {proc.returncode}"))
        sys.exit(proc.returncode)

    # ``importlib.metadata`` may cache distribution info within this
    # process; query in a fresh subprocess so the result reflects the
    # post-install state.
    new_version = _query_installed_version_fresh()
    if new_version is None:
        emit_md_err(fmt_error(
            "pip reported success but the installed version could not "
            "be re-queried. Run `pip show memorytalk` to verify."
        ))
        sys.exit(1)
    if new_version.strip() != latest.strip():
        emit_md_err(fmt_error(
            f"pip reported success but installed version is "
            f"`{new_version}`, expected `{latest}`. The pip you ran may "
            f"belong to a different Python — verify with "
            f"`{sys.executable} -m pip show {PACKAGE}`."
        ))
        sys.exit(1)

    click.echo(f"\n✓ upgraded to {new_version}")
    click.echo(
        "\n⚠ If the server is running, restart it to load the new code:\n"
        "    memory.talk server stop && memory.talk server start"
    )


# ────────── helpers ──────────


def _current_version() -> str | None:
    try:
        return importlib.metadata.version(PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return None


def _fetch_latest_pypi_version() -> str | None:
    """Hit ``https://pypi.org/pypi/<pkg>/json`` and return ``info.version``.

    Returns the most recent **stable** release (PyPI's JSON ``info.version``
    excludes pre-releases by default). Network / parse failures return
    ``None`` so the caller can produce a friendly error.
    """
    try:
        req = Request(PYPI_URL, headers={"User-Agent": f"{PACKAGE}-cli/upgrade"})
        with urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError, OSError):
        return None
    version = data.get("info", {}).get("version")
    return str(version) if version else None


def _query_installed_version_fresh() -> str | None:
    """Run a one-shot Python subprocess to query the installed version.

    Avoids ``importlib.metadata`` cache surprises that can linger inside
    a long-running CLI process after we've just modified site-packages.
    """
    code = (
        "import importlib.metadata, sys\n"
        "try: sys.stdout.write(importlib.metadata.version('memorytalk'))\n"
        "except importlib.metadata.PackageNotFoundError: sys.exit(2)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None
