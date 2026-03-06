"""export command - export conversation data."""
import json
import sys

import click
import requests
import yaml


SERVER_URL = "http://localhost:7788"


@click.command("export")
@click.argument("session")
@click.argument("platform", required=False)
@click.option("--server", default=SERVER_URL, help="Server URL")
@click.option("--format", "output_format", type=click.Choice(["json", "yaml"]), default="json", help="Output format")
@click.option("--output", "-o", help="Output file (default: stdout)")
def export(session: str, platform: str, server: str, output_format: str, output: str):
    """Export a conversation.

    Examples:
        memory-talk export session123
        memory-talk export session123 chatgpt --format yaml
    """
    if not platform:
        click.echo("Error: Platform is required", err=True)
        click.echo("Usage: memory-talk export <session> <platform>", err=True)
        sys.exit(1)

    url = f"{server}/api/conversations/{platform}/{session}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Format output
        if output_format == "yaml":
            output_data = yaml.dump(data, default_flow_style=False)
        else:
            output_data = json.dumps(data, indent=2, ensure_ascii=False)

        if output:
            with open(output, "w") as f:
                f.write(output_data)
            click.echo(f"Exported to {output}")
        else:
            click.echo(output_data)

    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to server at {server}", err=True)
        click.echo("Make sure the server is running with 'memory-talk serve start'", err=True)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            click.echo(f"Error: Conversation not found: {platform}/{session}", err=True)
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
