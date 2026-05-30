"""Claude Code host adapter."""
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


class ClaudeCodeAdapter:
    name = "claude-code"
    display_name = "Claude Code"
    needs_trust = False
    asset_subdir = "claude_code"

    def detect(self) -> HostPresence | None:
        path = shutil.which("claude")
        if not path:
            return None
        try:
            out = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            # Claude prints "2.1.157 (Claude Code)" → keep just the semver.
            m = re.match(r"^\s*([\d.]+)", out.stdout or "")
            version = m.group(1) if m else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            version = None
        return HostPresence(binary_path=Path(path), version=version)

    def current_state(self, materialized_dir: Path) -> HostState:
        listing = _capture(["claude", "plugin", "list"])
        # Find the block headed by "❯ memory-talk-recall@memory-talk" and
        # the "Status:" line that follows.
        m = re.search(
            rf"❯\s*{re.escape(PLUGIN_QUALIFIED)}\b(?P<block>.*?)(?=\n\s*❯|\Z)",
            listing, flags=re.DOTALL,
        )
        if m is None:
            return HostState.ABSENT
        block = m.group("block")
        if "failed to load" in block.lower():
            return HostState.INSTALLED_FAILED
        if re.search(r"Status:.*disabled", block, re.IGNORECASE):
            return HostState.INSTALLED_DISABLED
        if not re.search(r"Status:.*enabled", block, re.IGNORECASE):
            # Unknown status: be conservative
            return HostState.INSTALLED_FAILED
        # Enabled; check for asset drift
        if bundled_hash(self.asset_subdir) != dir_hash(materialized_dir):
            return HostState.INSTALLED_DRIFT
        return HostState.INSTALLED

    def install(self, materialized_dir: Path) -> None:
        if not self._marketplace_registered():
            _run(["claude", "plugin", "marketplace", "add", str(materialized_dir)])
        if not self._plugin_installed():
            _run(["claude", "plugin", "install", PLUGIN_QUALIFIED])
        else:
            # Re-materialized assets: refresh marketplace cache + re-enable.
            _run(["claude", "plugin", "marketplace", "update", MARKETPLACE],
                 allow_fail=True)
            _run(["claude", "plugin", "enable", PLUGIN_QUALIFIED], allow_fail=True)

    def uninstall(self) -> None:
        if self._plugin_installed():
            _run(["claude", "plugin", "uninstall", PLUGIN_QUALIFIED],
                 allow_fail=True)
        if self._marketplace_registered():
            _run(["claude", "plugin", "marketplace", "remove", MARKETPLACE],
                 allow_fail=True)

    def trust_ok(self) -> bool:
        return True

    def probe_command(self, token: str) -> list[str]:
        return [
            "claude", "-p",
            "--permission-mode", "bypassPermissions",
            "--model", "haiku",
            token,
        ]

    def _marketplace_registered(self) -> bool:
        out = _capture(["claude", "plugin", "marketplace", "list"])
        return bool(re.search(rf"❯\s*{re.escape(MARKETPLACE)}\b", out))

    def _plugin_installed(self) -> bool:
        out = _capture(["claude", "plugin", "list"])
        return bool(re.search(rf"❯\s*{re.escape(PLUGIN_QUALIFIED)}\b", out))


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
