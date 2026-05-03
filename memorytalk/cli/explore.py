"""CLI: explore list / detail / auto / manual / resume.

explore is a card-extraction workbench: it launches Claude Code in a
dedicated cwd (default ``~/.memory-talk/explore``) so the resulting
sessions are namespace-isolated and the recall hook gets suppressed
(see cli/recall.py).

list / detail read directly from ``~/.claude/projects/<project_id>/*.jsonl``
— no sync needed for fast feedback after an exploration run.

manual / resume use ``os.execvp`` to replace the memory-talk process
with claude itself, so the TUI owns the tty cleanly. The pure helper
``_resolve_exec_args`` is split out for testability.

auto is stubbed (exit 1) — the orchestration loop is planned for a
later release.
"""
from __future__ import annotations
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import click

from memorytalk.cli._format import (
    fmt_error, fmt_explore_detail, fmt_explore_list,
)
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config
from memorytalk.util.cc_project import claude_project_dir


@click.group("explore")
def explore() -> None:
    """Card-extraction workbench (launches Claude Code in an isolated cwd)."""


# ---------- shared helpers ----------

def _explore_cwd(cfg: Config) -> Path:
    return Path(cfg.settings.explore.cwd).expanduser().resolve()


def _ensure_explore_cwd(cwd: Path) -> None:
    """Create the explore cwd if missing. Refuse if it exists but is a file."""
    if cwd.exists() and not cwd.is_dir():
        raise click.ClickException(f"explore cwd is not a directory: {cwd}")
    cwd.mkdir(parents=True, exist_ok=True)


@dataclass
class _Record:
    session_uuid: str
    session_id: str             # sess_<uuid>
    started_at: str | None      # ISO8601 string from first round, or None
    last_at: str | None         # ISO8601 from last round
    rounds: int
    cards: int
    status: str                 # "active" | "done" | "abandoned"
    path: Path                  # local jsonl path

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "session_uuid": self.session_uuid,
            "started_at": self.started_at,
            "last_at": self.last_at,
            "rounds": self.rounds,
            "cards": self.cards,
            "status": self.status,
            "path": str(self.path),
        }


def _scan_jsonl(path: Path) -> _Record | None:
    """Parse a Claude Code session jsonl into a summary record.

    Best-effort: malformed lines are silently skipped. Returns None if
    the file is empty or fully unparseable.
    """
    rounds = 0
    cards = 0
    started: str | None = None
    last: str | None = None

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        rounds += 1
        ts = msg.get("timestamp")
        if isinstance(ts, str):
            if started is None:
                started = ts
            last = ts
        # Card-creation heuristic: scan tool_use blocks for the
        # `memory-talk card` command. Both Bash tool_use and direct
        # invocations are counted; precision is not the point — fast
        # feedback is. Doc says explicitly this is approximate.
        content = msg.get("message", {}).get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                inp = block.get("input")
                if isinstance(inp, dict):
                    cmd = inp.get("command")
                    if isinstance(cmd, str) and "memory-talk card" in cmd:
                        cards += 1

    if rounds == 0:
        return None

    return _Record(
        session_uuid=path.stem,
        session_id=f"sess_{path.stem}",
        started_at=started,
        last_at=last,
        rounds=rounds,
        cards=cards,
        status=_status_for(last, rounds, path),
        path=path,
    )


def _status_for(last_iso: str | None, rounds: int, path: Path) -> str:
    """Heuristic status from the last round timestamp + round count.

    - active: last activity < 30 min ago
    - abandoned: rounds < 3 AND last activity > 1 hr ago
    - done: everything else
    """
    ref: datetime | None = None
    if last_iso:
        try:
            ref = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        except ValueError:
            ref = None
    if ref is None:
        # Fall back to file mtime
        try:
            ref = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return "done"

    age_sec = (datetime.now(timezone.utc) - ref).total_seconds()
    if age_sec < 30 * 60:
        return "active"
    if rounds < 3 and age_sec > 60 * 60:
        return "abandoned"
    return "done"


def _list_records(cwd: Path) -> list[_Record]:
    """Enumerate all session jsonls under the explore project dir.

    Sorted by `started_at` desc (most recent first). Files with no
    parseable rounds are dropped.
    """
    project_dir = claude_project_dir(cwd)
    if not project_dir.is_dir():
        return []
    records: list[_Record] = []
    for path in project_dir.glob("*.jsonl"):
        r = _scan_jsonl(path)
        if r is not None:
            records.append(r)
    # Sort newest first; missing started_at sorts last.
    records.sort(key=lambda r: r.started_at or "", reverse=True)
    return records


def _resolve_exec_args(
    explore_cwd: Path, session_uuid: str | None,
) -> tuple[Path, list[str]]:
    """Build (cwd, argv) for manual/resume. Pure — no side effects.

    ``session_uuid`` is None for `manual`, set for `resume`. Strips a
    `sess_` prefix if the caller passed the memory-talk-shaped id.
    """
    if session_uuid is None:
        return explore_cwd, ["claude"]
    uuid = session_uuid[len("sess_"):] if session_uuid.startswith("sess_") else session_uuid
    return explore_cwd, ["claude", "--resume", uuid]


def _do_exec(cwd: Path, argv: list[str]) -> None:
    """Replace this process with claude. Never returns on success."""
    os.chdir(cwd)
    try:
        os.execvp(argv[0], argv)
    except FileNotFoundError as e:
        raise click.ClickException(
            f"`{argv[0]}` not found in PATH. Install Claude Code first."
        ) from e


# ---------- subcommands ----------

@explore.command("list")
@click.option("--limit", type=int, default=None, help="Cap the number of records.")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def list_cmd(limit: int | None, data_root: str | None, json_out: bool) -> None:
    """List exploration records (Claude Code sessions in explore cwd)."""
    cfg = Config(data_root) if data_root else Config()
    cwd = _explore_cwd(cfg)
    records = _list_records(cwd)
    if limit is not None:
        records = records[:limit]

    payload = {
        "explore_cwd": str(cwd),
        "records": [r.to_dict() for r in records],
    }
    if json_out:
        emit_json(payload)
    else:
        emit_md(fmt_explore_list(payload))


@explore.command("detail")
@click.argument("session_id")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def detail_cmd(session_id: str, data_root: str | None, json_out: bool) -> None:
    """Show one exploration record (rounds + cards extracted)."""
    cfg = Config(data_root) if data_root else Config()
    cwd = _explore_cwd(cfg)
    uuid = session_id[len("sess_"):] if session_id.startswith("sess_") else session_id
    path = claude_project_dir(cwd) / f"{uuid}.jsonl"
    if not path.is_file():
        msg = f"session not found in explore namespace: {session_id}"
        if json_out:
            emit_json_err(msg)
        else:
            emit_md_err(fmt_error(msg))
        sys.exit(1)
    record = _scan_jsonl(path)
    if record is None:
        msg = f"session jsonl is empty or unreadable: {path}"
        if json_out:
            emit_json_err(msg)
        else:
            emit_md_err(fmt_error(msg))
        sys.exit(1)
    if json_out:
        emit_json(record.to_dict())
    else:
        emit_md(fmt_explore_detail(record.to_dict()))


@explore.command("auto")
@click.option("--limit", type=int, default=None, help="Cap sessions processed.")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def auto_cmd(limit: int | None, data_root: str | None, json_out: bool) -> None:
    """Stub — non-interactive auto-extraction. Not yet implemented."""
    msg = "explore auto is not implemented yet (planned for a later release)"
    if json_out:
        emit_json_err(msg)
    else:
        emit_md_err(fmt_error(msg))
    sys.exit(1)


@explore.command("manual")
@click.option("--data-root", type=click.Path(), default=None)
def manual_cmd(data_root: str | None) -> None:
    """Drop into Claude Code in the explore cwd (interactive)."""
    cfg = Config(data_root) if data_root else Config()
    cwd = _explore_cwd(cfg)
    _ensure_explore_cwd(cwd)
    cwd_, argv = _resolve_exec_args(cwd, None)
    _do_exec(cwd_, argv)


@explore.command("resume")
@click.argument("session_id")
@click.option("--data-root", type=click.Path(), default=None)
def resume_cmd(session_id: str, data_root: str | None) -> None:
    """Resume an existing exploration session (interactive)."""
    cfg = Config(data_root) if data_root else Config()
    cwd = _explore_cwd(cfg)
    _ensure_explore_cwd(cwd)
    uuid = session_id[len("sess_"):] if session_id.startswith("sess_") else session_id
    # Refuse if the session isn't actually one of ours — avoids
    # accidentally pulling a work session into the explore namespace.
    expected = claude_project_dir(cwd) / f"{uuid}.jsonl"
    if not expected.is_file():
        raise click.BadParameter(
            f"session {session_id!r} is not in the explore namespace ({expected})",
            param_hint="SESSION_ID",
        )
    cwd_, argv = _resolve_exec_args(cwd, uuid)
    _do_exec(cwd_, argv)
