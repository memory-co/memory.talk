"""memory-talk v3 CLI root.

Each command is in its own submodule and registered here. Missing
modules are skipped silently so partial-build environments still expose
``--help`` (useful during incremental implementation).
"""
from __future__ import annotations
import click


@click.group()
@click.version_option(message="%(version)s")
def main() -> None:
    """memory-talk v3."""


# Register subcommands. Module name = command name (with one exception
# noted inline). Missing modules are ignored so an in-flight v3 build
# still has a usable `--help`.
_COMMANDS = ("server", "read", "setup", "sync", "search", "card", "review", "recall")

for _name in _COMMANDS:
    try:
        _mod = __import__(f"memorytalk.cli.{_name}", fromlist=[_name])
        main.add_command(getattr(_mod, _name))
    except ImportError:
        pass
