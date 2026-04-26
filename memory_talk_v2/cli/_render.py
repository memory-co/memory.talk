"""Output rendering for v2 CLI.

Two contracts:
- **Markdown** (default): emit Markdown text. If the target stream is a TTY,
  render with rich; otherwise emit the raw Markdown so pipes / scripts /
  LLMs see clean text.
- **JSON** (`--json`): always emit raw JSON (UTF-8, ensure_ascii=False).

Errors:
- Markdown mode → `**error:** <msg>` to stderr, exit 1
- JSON mode    → `{"error": ...}` to stdout, exit 1
"""
from __future__ import annotations
import json
import sys
from typing import Any


def _render_md_to(stream, text: str) -> None:
    if stream.isatty():
        # Lazy-import rich so non-TTY scripts don't pay the import cost.
        from rich.console import Console
        from rich.markdown import Markdown
        Console(file=stream).print(Markdown(text))
    else:
        stream.write(text)
        if not text.endswith("\n"):
            stream.write("\n")


def emit_md(text: str) -> None:
    """Markdown to stdout — rendered when TTY, raw otherwise."""
    _render_md_to(sys.stdout, text)


def emit_md_err(text: str) -> None:
    """Markdown to stderr — rendered when stderr is a TTY, raw otherwise."""
    _render_md_to(sys.stderr, text)


def emit_json(data: Any) -> None:
    """JSON to stdout."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def emit_json_err(payload: Any) -> None:
    """JSON error envelope to stdout (per the docs contract: --json errors
    use the same stream as --json successes)."""
    sys.stdout.write(json.dumps({"error": payload}, ensure_ascii=False) + "\n")
