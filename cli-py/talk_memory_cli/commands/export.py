"""export command - export conversations."""
import click
import requests
import sys
import json


SERVER_URL = "http://localhost:7900"


@click.command("export")
@click.argument("session_id")
@click.option("--platform", default="chatgpt", help="Platform name")
@click.option("--format", "output_format", default="json", type=click.Choice(["json", "md", "text"]), help="Output format")
@click.option("--output", "-o", help="Output file (default: stdout)")
@click.option("--server", default=SERVER_URL, help="Server URL")
def export(session_id: str, platform: str, output_format: str, output: str, server: str):
    """Export a conversation.

    Examples:
        talk-memory export abc-123
        talk-memory export abc-123 --platform chatgpt --format md
    """
    url = f"{server}/api/conversations/{platform}/{session_id}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        messages = data.get("messages", [])
        metadata = data.get("metadata", {})

        if output_format == "json":
            content = json.dumps(data, indent=2, ensure_ascii=False)
        elif output_format == "md":
            content = format_as_markdown(metadata, messages)
        else:  # text
            content = format_as_text(metadata, messages)

        if output:
            with open(output, "w") as f:
                f.write(content)
            click.echo(f"Exported to {output}")
        else:
            click.echo(content)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            click.echo(f"Error: Conversation '{session_id}' not found on platform '{platform}'", err=True)
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to server at {server}", err=True)
        click.echo("Make sure the server is running with 'talk-memory serve'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def format_as_markdown(metadata: dict, messages: list) -> str:
    """Format conversation as Markdown."""
    lines = []
    lines.append(f"# {metadata.get('title', 'Untitled')}\n")
    lines.append(f"**Platform:** {metadata.get('platform', 'unknown')}")
    lines.append(f"**Session ID:** {metadata.get('session_id', 'unknown')}")
    lines.append(f"**Created:** {metadata.get('created_at', 'unknown')}")
    lines.append(f"**Messages:** {len(messages)}\n")
    lines.append("---\n")

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")

        lines.append(f"### {role.capitalize()} ({timestamp})\n")
        lines.append(content)
        lines.append("\n")

    return "\n".join(lines)


def format_as_text(metadata: dict, messages: list) -> str:
    """Format conversation as plain text."""
    lines = []
    lines.append(metadata.get('title', 'Untitled'))
    lines.append("=" * 50)
    lines.append("")

    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        lines.append(f"[{role}] {content}")
        lines.append("")

    return "\n".join(lines)
