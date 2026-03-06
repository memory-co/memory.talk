"""Main CLI entry point for memory-talk."""
import click

from memory_talk.commands import serve, status as status_cmd, list as list_cmd, search, export


@click.group()
@click.version_option()
def main():
    """memory-talk: Manage conversation data from various chat platforms."""
    pass


# Register commands
main.add_command(serve.serve)
main.add_command(status_cmd.status)
main.add_command(list_cmd.list_cmd)
main.add_command(search.search)
main.add_command(export.export)


if __name__ == "__main__":
    main()
