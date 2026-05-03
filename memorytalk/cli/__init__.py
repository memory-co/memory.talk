"""memory-talk v2 CLI root."""
from __future__ import annotations
import click

from memorytalk.cli.server import server


@click.group()
def main() -> None:
    """memory-talk v2."""


main.add_command(server)

# Other command groups are attached as they're implemented.
for _name in ("card", "tag", "link", "sync", "search", "recall", "review", "view", "log", "rebuild", "setup", "filter"):
    try:
        _mod = __import__(f"memorytalk.cli.{_name}", fromlist=[_name])
        # `filter` shadows a builtin → the command object is named `filter_`
        # in the module; everything else uses the same name as the module.
        attr = "filter_" if _name == "filter" else _name
        main.add_command(getattr(_mod, attr))
    except ImportError:
        pass
