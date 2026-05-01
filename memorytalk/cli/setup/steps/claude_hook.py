"""Wizard step: install/refresh the UserPromptSubmit hook in
``~/.claude/settings.json`` so Claude Code calls ``memory-talk recall
--hook`` on every user prompt.

Gate (both required, AND):
  - ``~/.claude/`` directory exists
  - ``claude`` binary resolves on $PATH

Idempotency: our entry is tagged ``"_source": "memory-talk"``. Any other
hooks (different events, different tools) are left untouched. A user who
deletes the tag has opted out of automatic management; we'll append a
new tagged entry next to theirs rather than rewriting it.

Failure-soft: corrupt JSON, permission errors, missing ~/.claude all
return a ``skipped`` status with a reason. The wizard never aborts on
hook install — it's a convenience step, not a correctness gate.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any

from memorytalk.util.console import err_console, section
from memorytalk.util.settings_io import write_settings_atomic


COMMAND = "memory-talk recall --hook"
SOURCE_TAG = "memory-talk"

ENTRY_TEMPLATE: dict[str, Any] = {
    "type": "command",
    "command": COMMAND,
    "async": False,
    "_source": SOURCE_TAG,
}


def _claude_dir() -> Path:
    """Re-resolve at call time so tests' Path.home() monkeypatch is honored."""
    return Path.home() / ".claude"


def _settings_path() -> Path:
    return _claude_dir() / "settings.json"


def _step_claude_hook() -> dict:
    """Install / refresh the UserPromptSubmit hook.

    Returns a dict consumed by the wizard summary:
      {"status": "installed" | "updated" | "unchanged" | "skipped",
       "reason": "<text>"  # only present when skipped}
    """
    section("Claude Code hook")

    claude_dir = _claude_dir()
    settings_path = _settings_path()

    # Gate: both ~/.claude/ AND `claude` on $PATH
    if not claude_dir.is_dir():
        err_console.print(
            "[dim]~/.claude not found — skipping Claude hook install[/dim]"
        )
        return {"status": "skipped", "reason": "Claude Code not detected (~/.claude missing)"}
    if shutil.which("claude") is None:
        err_console.print(
            "[dim]`claude` not on $PATH — skipping Claude hook install[/dim]"
        )
        return {"status": "skipped", "reason": "Claude Code not detected (claude not on $PATH)"}

    # Read existing settings (or {} if missing)
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            err_console.print(
                f"[yellow]warning:[/yellow] {settings_path} is corrupt JSON — skipping ({e})"
            )
            return {"status": "skipped", "reason": "settings.json corrupt"}
        if not isinstance(data, dict):
            err_console.print(
                f"[yellow]warning:[/yellow] {settings_path} is not a JSON object — skipping"
            )
            return {"status": "skipped", "reason": "settings.json corrupt"}
    else:
        data = {}

    # Locate or create the UserPromptSubmit array
    hooks_root = data.setdefault("hooks", {})
    if not isinstance(hooks_root, dict):
        err_console.print(
            f"[yellow]warning:[/yellow] hooks field in {settings_path} is not an object — skipping"
        )
        return {"status": "skipped", "reason": "settings.json corrupt"}
    ups_blocks = hooks_root.setdefault("UserPromptSubmit", [])
    if not isinstance(ups_blocks, list):
        err_console.print(
            f"[yellow]warning:[/yellow] UserPromptSubmit in {settings_path} is not a list — skipping"
        )
        return {"status": "skipped", "reason": "settings.json corrupt"}

    # Search for our existing tagged entry
    existing_entry: dict | None = None
    for block in ups_blocks:
        if not isinstance(block, dict):
            continue
        for entry in block.get("hooks", []) or []:
            if isinstance(entry, dict) and entry.get("_source") == SOURCE_TAG:
                existing_entry = entry
                break
        if existing_entry is not None:
            break

    if existing_entry is None:
        ups_blocks.append({"hooks": [dict(ENTRY_TEMPLATE)]})
        action = "installed"
    else:
        # Diff canonical fields only; preserve user-added unknown fields
        diffed = any(existing_entry.get(k) != v for k, v in ENTRY_TEMPLATE.items())
        if not diffed:
            err_console.print("[green]✓[/green] Claude hook already correct")
            return {"status": "unchanged"}
        for k, v in ENTRY_TEMPLATE.items():
            existing_entry[k] = v
        action = "updated"

    # Atomic write
    try:
        write_settings_atomic(settings_path, data)
    except OSError as e:
        err_console.print(
            f"[yellow]warning:[/yellow] write to {settings_path} failed ({e})"
        )
        return {"status": "skipped", "reason": f"write failed: {e}"}

    err_console.print(f"[green]✓[/green] Claude hook {action} → {settings_path}")
    return {"status": action}
