"""Click CLI for memory.talk — server management and API client."""
from __future__ import annotations
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import click
import httpx

BASE_URL = "http://127.0.0.1:7788"


def _api(method: str, path: str, **kwargs) -> dict | list | None:
    """Call the memory.talk API. Prints error and exits if server is not running."""
    url = f"{BASE_URL}{path}"
    try:
        resp = httpx.request(method, url, timeout=30.0, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        click.echo(json.dumps({"error": "Server not running. Start with: memory-talk server start"}), err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = {"error": e.response.text}
        click.echo(json.dumps(detail), err=True)
        sys.exit(1)


@click.group()
def main():
    """memory.talk — persistent cross-session memory for AI agents."""
    pass


# ── Server commands ──────────────────────────────────────────

@main.group()
def server():
    """Manage the memory.talk server."""
    pass


@server.command("start")
@click.option("--data-root", default=None, help="Data root directory")
@click.option("--port", default=7788, help="Port to listen on")
def server_start(data_root: str | None, port: int):
    """Start the memory.talk server."""
    from memory_talk.config import Config
    config = Config(data_root) if data_root else Config()
    config.ensure_dirs()

    pid_path = config.pid_path

    # Check if already running
    if pid_path.exists():
        pid = int(pid_path.read_text().strip())
        try:
            os.kill(pid, 0)
            click.echo(json.dumps({"status": "already_running", "pid": pid, "port": port}))
            return
        except OSError:
            pid_path.unlink()

    env = os.environ.copy()
    if data_root:
        env["MEMORY_TALK_DATA_ROOT"] = str(data_root)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "memory_talk.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    pid_path.write_text(str(proc.pid))
    click.echo(json.dumps({"status": "started", "pid": proc.pid, "port": port}))


@server.command("stop")
@click.option("--data-root", default=None, help="Data root directory")
def server_stop(data_root: str | None):
    """Stop the memory.talk server."""
    from memory_talk.config import Config
    config = Config(data_root) if data_root else Config()
    pid_path = config.pid_path

    if not pid_path.exists():
        click.echo(json.dumps({"status": "not_running"}))
        return

    pid = int(pid_path.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(json.dumps({"status": "stopped", "pid": pid}))
    except OSError:
        click.echo(json.dumps({"status": "not_running", "pid": pid}))
    finally:
        pid_path.unlink(missing_ok=True)


@server.command("status")
@click.option("--data-root", default=None, help="Data root directory")
def server_status(data_root: str | None):
    """Check if the memory.talk server is running."""
    from memory_talk.config import Config
    config = Config(data_root) if data_root else Config()
    pid_path = config.pid_path

    if not pid_path.exists():
        click.echo(json.dumps({"status": "not_running"}))
        return

    pid = int(pid_path.read_text().strip())
    try:
        os.kill(pid, 0)
        click.echo(json.dumps({"status": "running", "pid": pid}))
    except OSError:
        pid_path.unlink(missing_ok=True)
        click.echo(json.dumps({"status": "not_running"}))


# ── Sync command ─────────────────────────────────────────────

@main.command()
@click.option("--data-root", default=None, help="Data root directory")
def sync(data_root: str | None):
    """Discover and import sessions from Claude Code."""
    from memory_talk.config import Config
    from memory_talk.storage.init_db import init_db
    from memory_talk.storage.sqlite import SQLiteStore
    from memory_talk.adapters.claude_code import ClaudeCodeAdapter

    config = Config(data_root) if data_root else Config()
    config.ensure_dirs()
    init_db(config.db_path)
    db = SQLiteStore(config.db_path)

    adapter = ClaudeCodeAdapter()
    files = adapter.discover()

    imported = 0
    skipped = 0
    errors = 0

    for fp in files:
        file_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
        if db.is_ingested(str(fp), file_hash):
            skipped += 1
            continue
        try:
            session = adapter.convert(fp)
            result = _api("POST", "/sessions", json=session.model_dump(mode="json"))
            if result:
                db.log_ingest(str(fp), session.session_id, file_hash)
                imported += 1
        except Exception as e:
            errors += 1
            click.echo(json.dumps({"error": str(e), "file": str(fp)}), err=True)

    click.echo(json.dumps({
        "status": "ok",
        "discovered": len(files),
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }))


# ── Sessions commands ────────────────────────────────────────

@main.group()
def sessions():
    """Manage sessions."""
    pass


@sessions.command("list")
@click.option("--tag", default=None, help="Filter by tag")
def sessions_list(tag: str | None):
    """List all sessions."""
    params = {}
    if tag:
        params["tag"] = tag
    result = _api("GET", "/sessions", params=params)
    click.echo(json.dumps(result))


@sessions.command("read")
@click.argument("session_id")
@click.option("--start", default=None, type=int, help="Start round index")
@click.option("--end", default=None, type=int, help="End round index")
def sessions_read(session_id: str, start: int | None, end: int | None):
    """Read a session's rounds."""
    params = {}
    if start is not None:
        params["start"] = start
    if end is not None:
        params["end"] = end
    result = _api("GET", f"/sessions/{session_id}", params=params)
    click.echo(json.dumps(result))


@sessions.group("tag")
def sessions_tag():
    """Manage session tags."""
    pass


@sessions_tag.command("add")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
def sessions_tag_add(session_id: str, tags: tuple[str, ...]):
    """Add tags to a session."""
    result = _api("POST", f"/sessions/{session_id}/tags", json={"tags": list(tags)})
    click.echo(json.dumps(result))


@sessions_tag.command("remove")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
def sessions_tag_remove(session_id: str, tags: tuple[str, ...]):
    """Remove tags from a session."""
    result = _api("DELETE", f"/sessions/{session_id}/tags", json={"tags": list(tags)})
    click.echo(json.dumps(result))


# ── Cards commands ───────────────────────────────────────────

@main.group()
def cards():
    """Manage cards."""
    pass


@cards.command("create")
@click.argument("card_json")
def cards_create(card_json: str):
    """Create a card from JSON string."""
    data = json.loads(card_json)
    result = _api("POST", "/cards", json=data)
    click.echo(json.dumps(result))


@cards.command("get")
@click.argument("card_id")
@click.option("--link-id", default=None, help="Link ID to refresh TTL")
def cards_get(card_id: str, link_id: str | None):
    """Get a card by ID."""
    params = {}
    if link_id:
        params["link_id"] = link_id
    result = _api("GET", f"/cards/{card_id}", params=params)
    click.echo(json.dumps(result))


@cards.command("list")
@click.option("--session-id", default=None, help="Filter by session ID")
def cards_list(session_id: str | None):
    """List all cards."""
    params = {}
    if session_id:
        params["session_id"] = session_id
    result = _api("GET", "/cards", params=params)
    click.echo(json.dumps(result))


# ── Links commands ───────────────────────────────────────────

@main.group()
def links():
    """Manage links."""
    pass


@links.command("create")
@click.argument("link_json")
def links_create(link_json: str):
    """Create a link from JSON string."""
    data = json.loads(link_json)
    result = _api("POST", "/links", json=data)
    click.echo(json.dumps(result))


@links.command("list")
@click.argument("id")
@click.option("--type", "type_filter", default=None, help="Filter by type")
def links_list(id: str, type_filter: str | None):
    """List links for an object."""
    params = {"id": id}
    if type_filter:
        params["type"] = type_filter
    result = _api("GET", "/links", params=params)
    click.echo(json.dumps(result))


# ── Recall command ───────────────────────────────────────────

@main.command()
@click.argument("query")
@click.option("--top-k", default=5, type=int, help="Number of results")
def recall(query: str, top_k: int):
    """Recall cards by semantic search."""
    result = _api("POST", "/recall", json={"query": query, "top_k": top_k})
    click.echo(json.dumps(result))


# ── Status command ───────────────────────────────────────────

@main.command()
def status():
    """Get server status and counts."""
    result = _api("GET", "/status")
    click.echo(json.dumps(result))


if __name__ == "__main__":
    main()
