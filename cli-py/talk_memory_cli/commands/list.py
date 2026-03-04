"""list command - list all conversations."""
import click
import requests
from datetime import datetime


SERVER_URL = "http://localhost:7900"


@click.command("list")
@click.argument("platform", required=False)
@click.option("--server", default=SERVER_URL, help="Server URL")
def list_cmd(platform: str, server: str):
    """List all conversations.

    Examples:
        talk-memory list
        talk-memory list chatgpt
    """
    url = f"{server}/api/conversations"
    if platform:
        url += f"?platform={platform}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        conversations = response.json()

        if not conversations:
            click.echo("No conversations found.")
            return

        # Format output
        click.echo(f"{'Platform':<15} {'Session ID':<20} {'Title':<30} {'Messages':<10} {'Updated':<20}")
        click.echo("-" * 95)

        for conv in conversations:
            title = conv.get("title", "")[:28]
            session_id = conv.get("session_id", "")[:18]
            platform_name = conv.get("platform", "")[:13]
            msg_count = str(conv.get("message_count", 0))[:8]
            updated = conv.get("updated_at", "")[:19]

            click.echo(f"{platform_name:<15} {session_id:<20} {title:<30} {msg_count:<10} {updated:<20}")

    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to server at {server}", err=True)
        click.echo("Make sure the server is running with 'talk-memory serve'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


import sys
