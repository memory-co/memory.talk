"""memory-talk v2 CLI root."""
from __future__ import annotations
import click

from memory_talk_v2.cli.server import server


@click.group()
def main() -> None:
    """memory-talk v2."""


main.add_command(server)

# Other command groups are attached as they're implemented.
for _name in ("card", "tag", "link", "sync", "search", "view", "log", "rebuild", "setup"):
    try:
        _mod = __import__(f"memory_talk_v2.cli.{_name}", fromlist=[_name])
        main.add_command(getattr(_mod, _name))
    except ImportError:
        pass
