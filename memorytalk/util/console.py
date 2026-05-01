"""Wizard / CLI console: rich output channel + questionary-backed prompts.

Two concerns live here:

1. **Output channel.** ``err_console`` is the single rich Console writing
   to stderr; ``section()`` prints the ``── Title ──`` banner that groups
   prompts. Wizard chatter goes here so the final markdown summary on
   stdout stays clean.

2. **Input prompts.** ``select / text / confirm`` wrap questionary so the
   wizard has one place to swap libraries and tests have one place to
   monkey-patch. ``Option`` separates a choice's stored value from its
   displayed label/description (used by the wizard's "common values +
   Other..." pattern).

Non-TTY fallback (piped stdin, e.g. the real-subprocess bootstrap test):
questionary needs prompt_toolkit which needs a real terminal. When
stdin/stdout aren't both ttys, ``select / text / confirm`` fall back to
plain numbered prompts echoed via ``err_console`` and read from stdin.

Wizard / step modules import as ``from memorytalk.cli import console``
and call ``console.select(...)`` etc. — that lets tests rebind names on
this module and have all callers see the patched versions.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from typing import Callable

import questionary
from questionary import Choice
from rich.console import Console


# --- output channel ---

err_console = Console(file=sys.stderr)


def section(title: str) -> None:
    """Print a category banner to stderr to group related prompts.

    Used by the wizard / step modules so the user always knows which
    bucket the next few questions belong to (Embedding / Storage /
    Server / PATH takeover). Goes to stderr so it doesn't pollute the
    final Markdown summary on stdout.
    """
    err_console.print(f"\n[bold cyan]── {title} ──[/bold cyan]")


# --- input prompts ---


@dataclass
class Option:
    """One row in a select() menu."""
    value: str
    title: str | None = None
    description: str | None = None

    @property
    def display(self) -> str:
        head = self.title if self.title is not None else self.value
        if self.description:
            return f"{head}  ·  {self.description}"
        return head


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def select(label: str, options: list[Option], default: str | None = None) -> str:
    """Arrow-key menu. Returns the chosen Option's ``value``.

    Non-interactive fallback: prints a numbered list and reads a line.
    Empty input (when a default is given) → default. Raises ``ValueError``
    on unrecognized input. EOF → ``KeyboardInterrupt``.
    """
    if _is_interactive():
        choices = [Choice(title=o.display, value=o.value) for o in options]
        default_choice = next((c for c in choices if c.value == default), None)
        answer = questionary.select(label, choices=choices, default=default_choice).ask()
        if answer is None:
            raise KeyboardInterrupt
        return answer

    err_console.print(f"? [bold]{label}[/bold]")
    for i, o in enumerate(options, 1):
        marker = "*" if default == o.value else " "
        err_console.print(f"  {marker} {i}. {o.display}")
    line = sys.stdin.readline()
    if not line:
        raise KeyboardInterrupt
    line = line.strip()
    if not line and default is not None:
        return default
    try:
        idx = int(line) - 1
        if 0 <= idx < len(options):
            return options[idx].value
    except ValueError:
        pass
    for o in options:
        if o.value == line:
            return o.value
    raise ValueError(f"invalid selection for {label!r}: {line!r}")


def text(
    label: str,
    default: str = "",
    validate: Callable[[str], bool | str] | None = None,
) -> str:
    """Free-text prompt. Empty input falls back to ``default``.

    ``validate`` may return ``True`` (ok) or an error message string.
    """
    if _is_interactive():
        answer = questionary.text(label, default=default, validate=validate).ask()
        if answer is None:
            raise KeyboardInterrupt
        return answer

    suffix = f" [{default}]" if default else ""
    err_console.print(f"? [bold]{label}[/bold]{suffix}")
    line = sys.stdin.readline()
    if not line:
        raise KeyboardInterrupt
    answer = line.rstrip("\n") or default
    if validate is not None:
        result = validate(answer)
        if result is not True:
            raise ValueError(result if isinstance(result, str) else "invalid input")
    return answer


def confirm(label: str, default: bool = True) -> bool:
    """y/n prompt — kept only for cases where the action is fully
    self-described in the label. For anything where description per
    option helps, use ``select`` with yes/no Options instead."""
    if _is_interactive():
        answer = questionary.confirm(label, default=default).ask()
        if answer is None:
            raise KeyboardInterrupt
        return answer

    suffix = "[Y/n]" if default else "[y/N]"
    err_console.print(f"? [bold]{label}[/bold] {suffix}")
    line = sys.stdin.readline()
    if not line:
        raise KeyboardInterrupt
    line = line.strip().lower()
    if not line:
        return default
    return line.startswith("y")
