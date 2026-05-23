"""Output rendering for v3 CLI.

Two contracts:

- **Markdown** (default): emit Markdown text. If the target stream is a
  TTY, render with rich; otherwise emit raw Markdown so pipes / scripts
  / LLMs see clean text.
- **JSON** (``--json``): always emit raw JSON (UTF-8, ensure_ascii=False).

Errors:

- Markdown mode → ``**error:** <msg>`` to stderr, exit 1
- JSON mode    → ``{"error": ...}`` to stdout, exit 1

Pager (opt-in per command, currently only ``read``):

- ``emit_md_paged`` wraps rich rendering in a less-style pager when
  both stdin and stdout are TTYs. Subprocess / pipe / ``--json`` paths
  fall through to plain output exactly like ``emit_md`` — AI tool
  invocations stay unaffected.
- Suppress with ``--no-pager`` (top-level flag) or ``NO_PAGER`` env
  var (the de-facto standard a few tools respect).
"""
from __future__ import annotations
import json
import os
import sys
from typing import Any


def _make_flat_markdown(text: str):
    """Build the rich Markdown renderable used by both direct print and
    pager paths. Left-aligned headings (rich's default centers H1/H2,
    which looks ugly with long ULID-bearing titles like ``CARD
    card_01KQ12E6R43JXMFDEKZ0292ZKZ``)."""
    from rich.markdown import Heading, Markdown

    class _FlatHeading(Heading):
        def __rich_console__(self, console, options):
            t = self.text
            t.justify = "left"
            t.stylize("bold")
            if self.tag == "h2":
                t.stylize("underline")
            yield t

    class _FlatMarkdown(Markdown):
        elements = {**Markdown.elements, "heading_open": _FlatHeading}

    return _FlatMarkdown(text)


def _render_md_to(stream, text: str) -> None:
    if stream.isatty():
        from rich.console import Console
        Console(file=stream).print(_make_flat_markdown(text))
    else:
        stream.write(text)
        if not text.endswith("\n"):
            stream.write("\n")


def emit_md(text: str) -> None:
    """Markdown to stdout — rendered when stdout is a TTY, raw otherwise."""
    _render_md_to(sys.stdout, text)


def _should_pager() -> bool:
    """Decide whether to route stdout through a scrollable pager.

    Both stdin and stdout must be a real TTY (``less`` needs keyboard
    input from stdin; a stdin pipe would make pager hang or fail). The
    ``NO_PAGER`` env var is checked too — the top-level ``--no-pager``
    CLI flag sets it, and external tooling that follows the de-facto
    convention can also opt out.
    """
    if os.environ.get("NO_PAGER"):
        return False
    return sys.stdout.isatty() and sys.stdin.isatty()


def emit_md_paged(text: str) -> None:
    """Markdown to stdout, scrollable via pager when in a real terminal.

    Falls back to plain ``emit_md`` for any non-TTY path (subprocess /
    pipe / redirect / ``NO_PAGER``) so AI tool invocations and shell
    pipelines stay unaffected. Pager command is ``$PAGER`` if set, else
    rich's default of ``less -RFX``-equivalent (auto-quit if short,
    keep output on screen, preserve ANSI styles).
    """
    if not _should_pager():
        emit_md(text)
        return
    # less needs -R to interpret ANSI escapes (otherwise rich's bold /
    # color sequences print as literal "ESC[1;4m..." text); -F to auto-
    # quit when output fits one screen so short payloads don't force an
    # interactive prompt; -X to leave the output on screen after quit.
    # ``pydoc.pager()`` (which rich's SystemPager uses) just execs
    # ``$PAGER`` with no flags, so we inject via the LESS env var like
    # git does (LESS=FRX is git's documented default). setdefault so a
    # user's existing $LESS preference wins.
    os.environ.setdefault("LESS", "FRX")
    from rich.console import Console
    console = Console()
    with console.pager(styles=True):
        console.print(_make_flat_markdown(text))


def emit_md_err(text: str) -> None:
    """Markdown to stderr — rendered when stderr is a TTY, raw otherwise."""
    _render_md_to(sys.stderr, text)


def emit_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def emit_json_err(payload: Any) -> None:
    """JSON error envelope to stdout (matches the contract: --json errors
    use the same stream as --json successes, so callers can pipe to jq)."""
    sys.stdout.write(json.dumps({"error": payload}, ensure_ascii=False) + "\n")
