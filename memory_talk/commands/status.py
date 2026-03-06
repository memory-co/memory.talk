"""status command - show server status."""
import click
import requests
import sys
from datetime import datetime


SERVER_URL = "http://localhost:7788"


@click.command("status")
@click.option("--server", default=SERVER_URL, help="Server URL")
def status(server: str):
    """Show server status and statistics.

    Examples:
        memory-talk status
        memory-talk status --server http://localhost:7900
    """
    # Check if server is running
    try:
        response = requests.get(f"{server}/health", timeout=2)
        if response.status_code != 200:
            click.echo("Server is not responding correctly", err=True)
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to server at {server}", err=True)
        click.echo("Make sure the server is running with 'memory-talk serve start'", err=True)
        sys.exit(1)

    # Get status
    try:
        response = requests.get(f"{server}/api/status")
        response.raise_for_status()
        data = response.json()

        click.echo("=== Server Status ===")
        click.echo(f"Version: {data.get('version', 'unknown')}")
        click.echo(f"Uptime: {data.get('uptime', 'unknown')}")
        click.echo()
        click.echo("=== Statistics ===")
        click.echo(f"Total Conversations: {data.get('total_conversations', 0)}")
        click.echo(f"Total Messages: {data.get('total_messages', 0)}")
        click.echo()

        sources = data.get('sources', [])
        click.echo("=== Sources ===")
        if sources:
            for source in sources:
                status_emoji = {
                    "running": "🟢",
                    "stopped": "⚪",
                    "error": "🔴",
                }.get(source.get('status', 'unknown'), "❓")

                click.echo(f"  {status_emoji} {source.get('name', 'unknown')}")
                click.echo(f"     Status: {source.get('status', 'unknown')}")
                click.echo(f"     Messages synced: {source.get('messages_synced', 0)}")

                last_sync = source.get('last_sync_time')
                if last_sync:
                    click.echo(f"     Last sync: {last_sync}")
                else:
                    click.echo(f"     Last sync: Never")
                click.echo()
        else:
            click.echo("  No sources configured")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
