"""Host adapter contract: each supported host CLI implements this."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class HostState(str, enum.Enum):
    ABSENT = "absent"
    INSTALLED = "installed"
    INSTALLED_DRIFT = "installed-drift"
    INSTALLED_UNTRUSTED = "installed-untrusted"
    INSTALLED_FAILED = "installed-failed"
    INSTALLED_DISABLED = "installed-disabled"
    INSTALLED_VERIFIED = "installed-verified"


@dataclass(frozen=True)
class HostPresence:
    """A host CLI was found in PATH."""
    binary_path: Path
    version: str | None


class HostAdapter(Protocol):
    """One AI CLI host (e.g. Claude Code, Codex). All methods must be cheap
    and side-effect-free except where annotated otherwise."""

    name: str
    display_name: str
    needs_trust: bool
    asset_subdir: str

    def detect(self) -> HostPresence | None:
        """Return presence info if the host CLI is on PATH, else None."""

    def current_state(self, materialized_dir: Path) -> HostState:
        """Detect the install state from on-disk state + ``host plugin list``."""

    def install(self, materialized_dir: Path) -> None:
        """Side-effect: register marketplace + install plugin. Idempotent on
        the host side (host CLIs error gracefully on re-add)."""

    def uninstall(self) -> None:
        """Side-effect: uninstall plugin + remove marketplace."""

    def trust_ok(self) -> bool:
        """Codex-only meaningful check; other hosts return True."""

    def probe_command(self, token: str) -> list[str]:
        """Argv to spawn the host with ``token`` as the user prompt. The
        spawn is expected to fire UserPromptSubmit; the recall command's
        probe short-circuit writes a sentinel keyed off ``token``."""
