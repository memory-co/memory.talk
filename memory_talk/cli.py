"""Main CLI entry point for memory-talk."""

import click

from memory_talk.commands import cards, explore, links, raw, recall, sessions, setup, status


@click.group()
@click.version_option()
def main():
    """memory-talk: Persistent cross-session memory for AI agents."""
    pass


main.add_command(setup.setup)
main.add_command(explore.explore)
main.add_command(sessions.sessions)
main.add_command(cards.cards)
main.add_command(links.links)
main.add_command(recall.recall)
main.add_command(raw.raw)
main.add_command(status.status)


if __name__ == "__main__":
    main()
