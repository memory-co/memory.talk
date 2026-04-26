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
        from rich.markdown import Heading, Markdown

        class _FlatHeading(Heading):
            """Left-aligned bold headings.

            rich's default Heading hard-codes H1 as a centered Panel and H2 as
            centered text. With long ULID-bearing titles like
            "CARD card_01KQ12E6R43JXMFDEKZ0292ZKZ", centering pushes the
            content way off the left margin. Override to keep all headings
            flush-left; H2 picks up an underline so the visual hierarchy is
            still legible.
            """
            def __rich_console__(self, console, options):
                t = self.text
                t.justify = "left"
                t.stylize("bold")
                if self.tag == "h2":
                    t.stylize("underline")
                yield t

        class _FlatMarkdown(Markdown):
            elements = {**Markdown.elements, "heading_open": _FlatHeading}

        Console(file=stream).print(_FlatMarkdown(text))
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
