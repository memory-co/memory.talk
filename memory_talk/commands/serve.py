"""serve command - manage the memory-talk server."""
import click
import os
import signal
import sys
from pathlib import Path


# PID file for server management
PID_FILE = Path.home() / ".talk-memory" / "server.pid"


@click.group()
def serve():
    """Manage the memory-talk server."""
    pass


@serve.command("start")
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=7788, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def start(host: str, port: int, reload: bool):
    """Start the memory-talk server."""
    # Check if already running
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            click.echo(f"Server is already running (PID: {pid})", err=True)
            click.echo("Use 'memory-talk serve stop' to stop it first", err=True)
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            PID_FILE.unlink()

    click.echo(f"Starting server at http://{host}:{port}")

    # Start server
    import subprocess
    cmd = [
        sys.executable, "-m", "uvicorn",
        "memory_talk.server:app",
        "--host", host,
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")

    # Save PID
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(cmd, cwd=str(Path(__file__).parent.parent.parent))

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    click.echo(f"Server started (PID: {proc.pid})")
    click.echo(f"Web interface: http://{host}:{port}")

    # Wait for the process
    try:
        proc.wait()
    except KeyboardInterrupt:
        click.echo("\nShutting down server...")
        proc.terminate()
        proc.wait()
        if PID_FILE.exists():
            PID_FILE.unlink()


@serve.command("stop")
def stop():
    """Stop the running memory-talk server."""
    if not PID_FILE.exists():
        click.echo("Server is not running (no PID file found)", err=True)
        sys.exit(1)

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Server stopped (PID: {pid})")
    except ProcessLookupError:
        click.echo("Server process not found, cleaning up PID file")
    except ValueError:
        click.echo("Invalid PID file, cleaning up")
        sys.exit(1)

    PID_FILE.unlink()


@serve.command("status")
def status():
    """Check if the server is running."""
    if not PID_FILE.exists():
        click.echo("Server is not running")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        click.echo(f"Server is running (PID: {pid})")
    except (ProcessLookupError, ValueError):
        click.echo("Server is not running (stale PID file)")
        if PID_FILE.exists():
            PID_FILE.unlink()
