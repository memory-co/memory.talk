"""search command - search conversations."""
import sys

import click
import requests


SERVER_URL = "http://localhost:7788"


@click.command("search")
@click.argument("query")
@click.argument("platform", required=False)
@click.option("--server", default=SERVER_URL, help="Server URL")
def search(query: str, platform: str, server: str):
    """Search conversations by keyword.

    Examples:
        memory-talk search "kubernetes"
        memory-talk search "deployment" chatgpt
    """
    url = f"{server}/api/search?q={click.utils.escape_query_param_value(query)}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        results = response.json()

        if not results:
            click.echo(f"No results found for '{query}'")
            return

        # Filter by platform if specified
        if platform:
            results = [r for r in results if r.get("platform") == platform]

        if not results:
            click.echo(f"No results found for '{query}' in platform '{platform}'")
            return

        click.echo(f"Found {len(results)} result(s):\n")

        for i, result in enumerate(results, 1):
            title = result.get("title", "Untitled")
            platform_name = result.get("platform", "")
            matched = result.get("matched_message", "")[:100]

            click.echo(f"{i}. [{platform_name}] {title}")
            click.echo(f"   {matched}...")
            click.echo()

    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to server at {server}", err=True)
        click.echo("Make sure the server is running with 'memory-talk serve start'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
