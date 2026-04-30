"""Wizard step: pick a single-or-multi-option provider.

Used for vector and relation backends today, where there's only one
option but we still want to surface the choice in the wizard summary.
"""
from __future__ import annotations

from rich.prompt import Prompt

from .._io import err_console


def _step_choice(label: str, choices: list[str], default: str) -> str:
    if len(choices) == 1:
        err_console.print(f"[bold]{label}[/bold]: only `{choices[0]}` available")
        return choices[0]
    return Prompt.ask(label, choices=choices, default=default, console=err_console)
