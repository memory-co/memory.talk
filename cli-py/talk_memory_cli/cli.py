"""Main CLI entry point for talk-memory."""
import click

from talk_memory_cli.commands import serve, pull, list_cmd, search, export


@click.group()
@click.version_option()
def main():
    """talk-memory: Manage conversation data from various chat platforms."""
    pass


# Register commands
main.add_command(serve.serve)
main.add_command(pull.pull)
main.add_command(list_cmd.list_cmd)
main.add_command(search.search)
main.add_command(export.export)


if __name__ == "__main__":
    main()
