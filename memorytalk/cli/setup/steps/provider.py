"""Wizard step: pick a single-or-multi-option provider.

Used for vector and relation backends. Single-option case still prints
a one-liner so the user knows the choice was surfaced; multi-option case
becomes a real arrow-key select.
"""
from __future__ import annotations

from memorytalk.util import console
from memorytalk.util.console import err_console


def _step_choice(label: str, choices: list[str], default: str) -> str:
    if len(choices) == 1:
        err_console.print(f"[bold]{label}[/bold]: only `{choices[0]}` available")
        return choices[0]
    options = [console.Option(c) for c in choices]
    return console.select(label, options, default=default)
