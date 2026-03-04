"""serve command - start the talk-memory server."""
import click
import subprocess
import sys


@click.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=7900, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(host: str, port: int, reload: bool):
    """Start the talk-memory server."""
    cmd = [
        sys.executable, "-m", "talk_memory_server",
        "--host", host,
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")

    click.echo(f"Starting server at http://{host}:{port}")
    subprocess.run(cmd)
