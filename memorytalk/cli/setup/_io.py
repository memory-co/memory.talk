"""Shared stderr Console for setup wizard chatter.

All wizard prompts / status lines go through this single Console so the
output channel is consistent and easy to capture in tests. The final
summary uses `cli/_render.emit_md` (stdout); errors use
`cli/_render.emit_md_err` (stderr, via this same Console implicitly).
"""
from __future__ import annotations
import sys

from rich.console import Console


err_console = Console(file=sys.stderr)


def section(title: str) -> None:
    """Print a category banner to stderr to group related prompts.

    Used by the wizard / step modules so the user always knows which
    bucket the next few questions belong to (Embedding / Storage /
    Server / PATH takeover). Goes to stderr so it doesn't pollute the
    final Markdown summary on stdout.
    """
    err_console.print(f"\n[bold cyan]── {title} ──[/bold cyan]")
