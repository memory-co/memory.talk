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
