"""pull command - trigger exporters to pull data."""
import click
import requests
import sys


SERVER_URL = "http://localhost:7900"


@click.command()
@click.argument("platform", required=False)
@click.option("--all", "pull_all", is_flag=True, help="Run all configured exporters")
@click.option("--server", default=SERVER_URL, help="Server URL")
def pull(platform: str, pull_all: bool, server: str):
    """Trigger exporters to pull conversation data.

    Examples:
        talk-memory pull chatgpt
        talk-memory pull --all
    """
    if not platform and not pull_all:
        click.echo("Error: Please specify a platform or use --all", err=True)
        sys.exit(1)

    # Note: This is a placeholder implementation
    # In a full implementation, this would trigger actual exporters
    click.echo(f"Pull command called for platform: {platform or 'all'}")

    if platform:
        click.echo(f"To pull from {platform}, you need to run the corresponding exporter.")
        click.echo(f"Exporters should POST to {server}/api/ingest")
    else:
        click.echo("To pull from all platforms, run each exporter separately.")
