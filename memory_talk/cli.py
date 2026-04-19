"""Click CLI for memory.talk — server management and API client."""
from __future__ import annotations
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click
import httpx

# Common option for output format — added to every leaf command
_fmt_option = click.option("-f", "--format", "fmt", type=click.Choice(["json", "text"]), default="json", help="Output format")


def _base_url(data_root=None) -> str:
    """Read port from settings, return base URL."""
    from memory_talk.config import Config
    config = Config(data_root) if data_root else Config()
    return f"http://127.0.0.1:{config.settings.server.port}"


def _output(data, fmt="json"):
    """Output data in the chosen format."""
    if fmt == "text":
        if isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    click.echo("---")
                    for k, v in item.items():
                        click.echo(f"  {k}: {v}")
                else:
                    click.echo(str(item))
        else:
            click.echo(str(data))
    else:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _api(method: str, path: str, data_root=None, **kwargs) -> dict | list | None:
    """Call the memory.talk API."""
    url = f"{_base_url(data_root)}{path}"
    try:
        resp = httpx.request(method, url, timeout=30.0, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        click.echo(json.dumps({"error": "Server not running. Start with: memory-talk server start"}, ensure_ascii=False), err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = {"error": e.response.text}
        click.echo(json.dumps(detail, ensure_ascii=False), err=True)
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
@_fmt_option
def server_start(data_root, fmt):
    """Start the memory.talk server."""
    from memory_talk.config import Config
    config = Config(data_root) if data_root else Config()
    config.ensure_dirs()
    port = config.settings.server.port

    pid_path = config.pid_path

    if pid_path.exists():
        pid = int(pid_path.read_text().strip())
        try:
            os.kill(pid, 0)
            _output({"status": "already_running", "pid": pid, "port": port}, fmt)
            return
        except OSError:
            pid_path.unlink()

    env = os.environ.copy()
    if data_root:
        env["MEMORY_TALK_DATA_ROOT"] = str(data_root)

    log_path = config.data_root / "server.log"
    log_file = open(log_path, "w")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "memory_talk.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
        start_new_session=True,
    )

    time.sleep(1.5)
    exit_code = proc.poll()

    if exit_code is not None:
        log_file.close()
        log_content = log_path.read_text()
        pid_path.unlink(missing_ok=True)
        error_tail = log_content[-500:] if len(log_content) > 500 else log_content
        _output({"status": "failed", "exit_code": exit_code, "error": error_tail}, fmt)
    else:
        log_file.close()
        pid_path.write_text(str(proc.pid))
        _output({"status": "started", "pid": proc.pid, "port": port}, fmt)


@server.command("stop")
@click.option("--data-root", default=None, help="Data root directory")
@_fmt_option
def server_stop(data_root, fmt):
    """Stop the memory.talk server."""
    from memory_talk.config import Config
    config = Config(data_root) if data_root else Config()
    pid_path = config.pid_path

    if not pid_path.exists():
        _output({"status": "not_running"}, fmt)
        return

    pid = int(pid_path.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        _output({"status": "stopped", "pid": pid}, fmt)
    except OSError:
        _output({"status": "not_running", "pid": pid}, fmt)
    finally:
        pid_path.unlink(missing_ok=True)


@server.command("status")
@click.option("--data-root", default=None, help="Data root directory")
@_fmt_option
def server_status(data_root, fmt):
    """Check if the memory.talk server is running."""
    from memory_talk.config import Config
    config = Config(data_root) if data_root else Config()

    base = {
        "data_root": str(config.data_root),
        "settings_path": str(config.settings_path),
    }

    # 直接调 API，能连上就是 running，连不上就是 not_running
    url = _base_url(data_root)
    try:
        resp = httpx.get(f"{url}/status", timeout=3)
        if resp.status_code == 200:
            _output({**base, "status": "running", **resp.json()}, fmt)
        else:
            _output({**base, "status": "running", "error": f"API 返回 {resp.status_code}"}, fmt)
    except httpx.ConnectError:
        _output({**base, "status": "not_running"}, fmt)


# ── Sync command ─────────────────────────────────────────────

@main.command()
@click.option("--data-root", default=None, help="Data root directory")
@_fmt_option
def sync(data_root, fmt):
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
            s = adapter.convert(fp)
            result = _api("POST", "/sessions", data_root=data_root, json=s.model_dump(mode="json"))
            if result:
                db.log_ingest(str(fp), s.session_id, file_hash)
                imported += 1
        except Exception as e:
            errors += 1
            click.echo(json.dumps({"error": str(e), "file": str(fp)}, ensure_ascii=False), err=True)

    _output({
        "status": "ok",
        "discovered": len(files),
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }, fmt)


# ── Session commands ────────────────────────────────────────

@main.group()
def session():
    """Manage sessions."""
    pass


@session.command("list")
@click.option("--tag", default=None, help="Filter by tag")
@_fmt_option
def session_list(tag, fmt):
    """List all sessions."""
    params = {}
    if tag:
        params["tag"] = tag
    result = _api("GET", "/sessions", params=params)
    _output(result, fmt)


@session.command("read")
@click.argument("session_id")
@click.option("--start", default=None, type=int, help="Start round index")
@click.option("--end", default=None, type=int, help="End round index")
@_fmt_option
def session_read(session_id, start, end, fmt):
    """Read a session's rounds."""
    params = {}
    if start is not None:
        params["start"] = start
    if end is not None:
        params["end"] = end
    result = _api("GET", f"/sessions/{session_id}", params=params)
    _output(result, fmt)


@session.group("tag")
def session_tag():
    """Manage session tags."""
    pass


@session_tag.command("add")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
@_fmt_option
def session_tag_add(session_id, tags, fmt):
    """Add tags to a session."""
    result = _api("POST", f"/sessions/{session_id}/tags", json={"tags": list(tags)})
    _output(result, fmt)


@session_tag.command("remove")
@click.argument("session_id")
@click.argument("tags", nargs=-1, required=True)
@_fmt_option
def session_tag_remove(session_id, tags, fmt):
    """Remove tags from a session."""
    result = _api("DELETE", f"/sessions/{session_id}/tags", json={"tags": list(tags)})
    _output(result, fmt)


# ── Card commands ───────────────────────────────────────────

@main.group()
def card():
    """Manage cards."""
    pass


@card.command("create")
@click.argument("card_json")
@_fmt_option
def card_create(card_json, fmt):
    """Create a card from JSON string."""
    data = json.loads(card_json)
    result = _api("POST", "/cards", json=data)
    _output(result, fmt)


@card.command("get")
@click.argument("card_id")
@click.option("--link-id", default=None, help="Link ID to refresh TTL")
@_fmt_option
def card_get(card_id, link_id, fmt):
    """Get a card by ID."""
    params = {}
    if link_id:
        params["link_id"] = link_id
    result = _api("GET", f"/cards/{card_id}", params=params)
    _output(result, fmt)


@card.command("list")
@click.option("--session-id", default=None, help="Filter by session ID")
@_fmt_option
def card_list(session_id, fmt):
    """List all cards."""
    params = {}
    if session_id:
        params["session_id"] = session_id
    result = _api("GET", "/cards", params=params)
    _output(result, fmt)


# ── Link commands ───────────────────────────────────────────

@main.group()
def link():
    """Manage links."""
    pass


@link.command("create")
@click.argument("link_json")
@_fmt_option
def link_create(link_json, fmt):
    """Create a link from JSON string."""
    data = json.loads(link_json)
    result = _api("POST", "/links", json=data)
    _output(result, fmt)


@link.command("list")
@click.argument("id")
@click.option("--type", "type_filter", default=None, help="Filter by type")
@_fmt_option
def link_list(id, type_filter, fmt):
    """List links for an object."""
    params = {"id": id}
    if type_filter:
        params["type"] = type_filter
    result = _api("GET", "/links", params=params)
    _output(result, fmt)


# ── Recall command ───────────────────────────────────────────

@main.command()
@click.argument("query")
@click.option("--top-k", default=5, type=int, help="Number of results")
@_fmt_option
def recall(query, top_k, fmt):
    """Recall cards by semantic search."""
    result = _api("POST", "/recall", json={"query": query, "top_k": top_k})
    _output(result, fmt)


# ── Search command ───────────────────────────────────────────

@main.command()
@click.argument("query")
@click.option("--where", "-w", default=None, help="Metadata filter DSL (see docs/cli/search.md)")
@click.option("--top-k", default=10, type=int, help="Per-branch cap (cards and sessions each)")
@_fmt_option
def search(query, where, top_k, fmt):
    """Hybrid search over cards and sessions with metadata filtering."""
    payload = {"query": query, "top_k": top_k}
    if where is not None:
        payload["where"] = where
    result = _api("POST", "/search", json=payload)
    _output(result, fmt)


@main.command()
@_fmt_option
def rebuild(fmt):
    """Rebuild SQLite + LanceDB index from files. Blocks until done."""
    from memory_talk.config import Config
    from memory_talk.service.rebuild import rebuild_sync
    config = Config()
    result = rebuild_sync(config)
    _output(result, fmt)


if __name__ == "__main__":
    main()
