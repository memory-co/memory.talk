"""Codex host adapter. Differs from Claude Code in two key ways:

1. The plugin uninstall verb is ``plugin remove``, not ``plugin uninstall``.
2. Codex requires *per-hook trust*: even an installed plugin won't fire
   until the user accepts the ``Hooks need review`` dialog in the TUI,
   which writes a ``trusted_hash`` under ``[hooks.state]`` in
   ``~/.codex/config.toml``. There is NO CLI to grant trust — the user
   must do it once in the TUI. The setup step pauses and waits.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from memorytalk.hooks.base import HostPresence, HostState
from memorytalk.hooks.materialize import bundled_hash, dir_hash


MARKETPLACE = "memory-talk"
PLUGIN = "memory-talk-recall"
PLUGIN_QUALIFIED = f"{PLUGIN}@{MARKETPLACE}"
TRUST_KEY = f"{PLUGIN_QUALIFIED}:hooks/hooks.json:user_prompt_submit:0:0"
CONFIG_PATH = Path("~/.codex/config.toml").expanduser()


class CodexAdapter:
    name = "codex"
    display_name = "Codex"
    needs_trust = True
    asset_subdir = "codex"

    def detect(self) -> HostPresence | None:
        path = shutil.which("codex")
        if not path:
            return None
        try:
            out = subprocess.run(
                ["codex", "--version"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            m = re.match(r"^\s*codex(?:-cli)?\s+([\d.]+)", out.stdout or "")
            if not m:
                m = re.match(r"^\s*([\d.]+)", out.stdout or "")
            version = m.group(1) if m else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            version = None
        return HostPresence(binary_path=Path(path), version=version)

    def current_state(self, materialized_dir: Path) -> HostState:
        listing = _capture(["codex", "plugin", "list"])
        # Codex's `plugin list` is a fixed-width table. Find the row for
        # our plugin and pull its STATUS column.
        # Sample row:
        #   memory-talk-recall@memory-talk     enabled    1    /home/...
        m = re.search(
            rf"^\s*{re.escape(PLUGIN_QUALIFIED)}\s+(?P<status>\S+(?:\s\S+)?)",
            listing, flags=re.MULTILINE,
        )
        if m is None:
            return HostState.ABSENT
        status = m.group("status").lower()
        if "not installed" in status or status == "available":
            return HostState.ABSENT
        if "failed" in status:
            return HostState.INSTALLED_FAILED
        if "disabled" in status:
            return HostState.INSTALLED_DISABLED
        # Installed/enabled — now check drift, then trust.
        if bundled_hash(self.asset_subdir) != dir_hash(materialized_dir):
            return HostState.INSTALLED_DRIFT
        if not self.trust_ok():
            return HostState.INSTALLED_UNTRUSTED
        return HostState.INSTALLED

    def install(self, materialized_dir: Path) -> None:
        if not self._marketplace_registered():
            _run(["codex", "plugin", "marketplace", "add", str(materialized_dir)])
        if not self._plugin_installed():
            _run(["codex", "plugin", "add", PLUGIN_QUALIFIED])
        else:
            _run(["codex", "plugin", "marketplace", "upgrade", MARKETPLACE],
                 allow_fail=True)

    def uninstall(self) -> None:
        if self._plugin_installed():
            _run(["codex", "plugin", "remove", PLUGIN_QUALIFIED], allow_fail=True)
        if self._marketplace_registered():
            _run(["codex", "plugin", "marketplace", "remove", MARKETPLACE],
                 allow_fail=True)

    def trust_ok(self) -> bool:
        if not CONFIG_PATH.exists():
            return False
        text = CONFIG_PATH.read_text(encoding="utf-8", errors="replace")
        # Look for the literal section header `[hooks.state."<TRUST_KEY>"]`
        # followed by a `trusted_hash = "sha256:..."` line. Cheap regex
        # avoids hauling in a full TOML parser at hook-install time.
        pattern = (
            rf'\[hooks\.state\."{re.escape(TRUST_KEY)}"\]'
            rf'[^\[]*?trusted_hash\s*=\s*"sha256:[0-9a-f]+"'
        )
        return bool(re.search(pattern, text, flags=re.DOTALL))

    def probe_command(self, token: str) -> list[str]:
        return ["codex", "exec", "--skip-git-repo-check", token]

    def _marketplace_registered(self) -> bool:
        out = _capture(["codex", "plugin", "marketplace", "list"])
        return bool(re.search(rf"\b{re.escape(MARKETPLACE)}\b", out))

    def _plugin_installed(self) -> bool:
        out = _capture(["codex", "plugin", "list"])
        m = re.search(
            rf"^\s*{re.escape(PLUGIN_QUALIFIED)}\s+(?P<status>\S+(?:\s\S+)?)",
            out, flags=re.MULTILINE,
        )
        if m is None:
            return False
        return "not installed" not in m.group("status").lower()


def _run(argv: list[str], *, allow_fail: bool = False) -> None:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        if allow_fail:
            return
        raise RuntimeError(f"{' '.join(argv)}: {e}") from e
    if r.returncode != 0 and not allow_fail:
        raise RuntimeError(
            f"{' '.join(argv)} exited {r.returncode}\n{r.stdout}\n{r.stderr}"
        )


def _capture(argv: list[str]) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return (r.stdout or "") + "\n" + (r.stderr or "")
