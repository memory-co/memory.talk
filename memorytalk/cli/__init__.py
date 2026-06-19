"""memory.talk v3 CLI root.

Each command is in its own submodule and registered here. Missing
modules are skipped silently so partial-build environments still expose
``--help`` (useful during incremental implementation).
"""
from __future__ import annotations
import os

import click


@click.group()
@click.version_option(message="%(version)s")
@click.option(
    "--no-pager", "no_pager", is_flag=True, default=False,
    help="Disable the scrollable pager (only applies to commands that "
         "opt-in — currently `read` and `search`). Equivalent to NO_PAGER=1.",
)
def main(no_pager: bool) -> None:
    """memory.talk v3."""
    # Propagate to env so the rendering layer (memorytalk.cli._render)
    # doesn't need to thread a click context everywhere. Subprocess and
    # ``--json`` paths bypass the pager regardless.
    if no_pager:
        os.environ["NO_PAGER"] = "1"


# Register subcommands. Module name = command name (with one exception
# noted inline). Missing modules are ignored so an in-flight v3 build
# still has a usable `--help`.
_COMMANDS = ("server", "read", "setup", "sync", "search", "card",
             "recall", "session", "explore", "upgrade")

for _name in _COMMANDS:
    try:
        _mod = __import__(f"memorytalk.cli.{_name}", fromlist=[_name])
        main.add_command(getattr(_mod, _name))
    except ImportError:
        pass
