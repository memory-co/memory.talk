"""CLI: setup — interactive idempotent install / configure / restart.

Walkthrough lives in ``docs/cli/v2/setup.md``. This module is the entry
point that:

1. Detects whether it's running from inside ``~/.memory-talk/.venv``
2. If not, bootstraps that venv (creates it + ``pip install memorytalk``)
   and re-execs itself so the rest of the wizard runs from the venv.
3. Once inside the venv, drives the configuration wizard (rich prompts).

`--data-root` is intentionally absent — setup is the bootstrap step, it
needs to anchor on a known location. data_root for *other* commands
remains overridable via the ``MEMORY_TALK_DATA_ROOT`` env var; setup
honors it for where ``settings.json`` lands, but the venv itself always
lives at ``~/.memory-talk/.venv``.
"""
from __future__ import annotations
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md, emit_md_err
from memorytalk.cli._setup_helpers import (
    create_symlink, diff_settings, humanize_paths,
    read_settings_raw, write_settings_atomic,
)
from memorytalk.cli.server import pid_alive, start_server_proc, stop_server_proc
from memorytalk.config import Config, Settings
from memorytalk.provider.embedding import (
    EmbedderValidationError, validate_embedder,
)


# All wizard chatter goes to stderr; the final summary goes to stdout via emit_md.
_err_console = Console(file=sys.stderr)


# ---------- venv paths ----------

def _venv_root() -> Path:
    """The dedicated memorytalk venv. Always at ~/.memory-talk/.venv,
    independent of MEMORY_TALK_DATA_ROOT (data + venv are decoupled)."""
    return Path.home() / ".memory-talk" / ".venv"


def _venv_python() -> Path:
    return _venv_root() / "bin" / "python"


def _venv_memory_talk() -> Path:
    return _venv_root() / "bin" / "memory-talk"


def _data_root() -> Path:
    """Where settings.json + sessions/cards/links/etc live. Honors
    MEMORY_TALK_DATA_ROOT env var; defaults to ~/.memory-talk."""
    env = os.environ.get("MEMORY_TALK_DATA_ROOT")
    return Path(env) if env else Path.home() / ".memory-talk"


def _already_in_venv() -> bool:
    """True iff the running interpreter is the dedicated venv's python."""
    try:
        return Path(sys.executable).resolve() == _venv_python().resolve()
    except OSError:
        return False


# ---------- bootstrap ----------

def _bootstrap_venv(*, upgrade: bool = False) -> None:
    """Make sure ~/.memory-talk/.venv exists and has memorytalk installed.

    - First call (venv missing): creates it, then pip install memorytalk.
    - Subsequent calls (venv present, --upgrade flag): pip install --upgrade.
    - Steady-state (venv present, --upgrade off): no-op.

    Source of memorytalk is PyPI by default. For tests / dev workflows
    that want to install from a local checkout instead, set the
    ``MEMORYTALK_BOOTSTRAP_SOURCE`` env var to a path or VCS URL — that
    value is passed verbatim to ``pip install``.
    """
    venv = _venv_root()
    py = _venv_python()
    pip = venv / "bin" / "pip"

    if not py.exists():
        _err_console.print(f"[dim]bootstrapping venv at {venv} ...[/dim]")
        venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)

    source = os.environ.get("MEMORYTALK_BOOTSTRAP_SOURCE", "memorytalk")
    extra = os.environ.get("MEMORYTALK_BOOTSTRAP_PIP_ARGS", "").split()
    cmd = [str(pip), "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(extra)
    cmd.append(source)

    if upgrade or not _venv_memory_talk().exists():
        _err_console.print(
            f"[dim]installing {'/'.join([source])} into {venv} "
            f"({'--upgrade' if upgrade else 'fresh'}) ...[/dim]"
        )
        subprocess.run(cmd, check=True)


def _reexec_into_venv() -> None:
    """Replace the current process with ``<venv>/bin/memory-talk <argv...>``.

    Intentionally does NOT return — on success the OS swaps the process
    image. On failure (rare: missing binary, permission, etc.) we surface
    a clean error and exit 1 instead of silently continuing in the wrong
    Python.
    """
    target = _venv_memory_talk()
    if not target.exists():
        emit_md_err(fmt_error(
            f"venv binary missing after bootstrap: {target} — install seems "
            "to have failed silently. Run with --upgrade to retry."
        ))
        sys.exit(1)
    try:
        os.execv(str(target), [str(target), *sys.argv[1:]])
    except OSError as e:
        emit_md_err(fmt_error(f"failed to re-exec into venv: {e}"))
        sys.exit(1)


# ---------- entry point ----------

@click.command("setup")
@click.option("--upgrade", is_flag=True, default=False,
              help="Force `pip install --upgrade memorytalk` in the dedicated venv.")
def setup(upgrade: bool) -> None:
    """Interactive wizard: install / reconfigure / restart memory-talk."""
    # 1. If we're not yet running inside ~/.memory-talk/.venv, bootstrap it
    #    and re-exec. After execv, the new process re-enters this function
    #    with `_already_in_venv()` returning True.
    if not _already_in_venv() or upgrade:
        try:
            _bootstrap_venv(upgrade=upgrade)
        except subprocess.CalledProcessError as e:
            emit_md_err(fmt_error(
                f"failed to bootstrap venv: {e}\n"
                "  check network connectivity and that pip can reach PyPI."
            ))
            sys.exit(1)
        if not _already_in_venv():
            _reexec_into_venv()
            # _reexec_into_venv() doesn't return on success
            return

    # 2. Inside the venv now — refuse to run against a v1 data root.
    cfg = Config(_data_root())
    try:
        cfg.validate()
    except Exception as e:
        emit_md_err(fmt_error(str(e)))
        sys.exit(1)

    try:
        old_raw = read_settings_raw(cfg.settings_path)
    except ValueError:
        # corrupt JSON — back up and re-init
        if not Confirm.ask(
            "settings.json is corrupted. Back it up to settings.json.bak and re-initialize?",
            console=_err_console, default=True,
        ):
            sys.exit(1)
        bak = cfg.settings_path.with_suffix(".json.bak")
        cfg.settings_path.replace(bak)
        old_raw = None
        _err_console.print(f"[dim]backed up corrupt settings → {bak}[/dim]")

    is_first_install = old_raw is None
    cfg.data_root.mkdir(parents=True, exist_ok=True)

    try:
        result = _wizard(cfg, old_raw, is_first_install)
    except KeyboardInterrupt:
        _err_console.print("\n[dim]aborted by user — no changes written[/dim]")
        sys.exit(130)

    emit_md(_summary_md(cfg, result))


# ---------- wizard ----------

def _wizard(cfg: Config, old_raw: dict | None, is_first_install: bool) -> dict:
    is_first_install_str = "首次安装" if is_first_install else "已有配置 — 修改模式"
    _err_console.print(f"[bold]memory-talk setup[/bold] · {is_first_install_str}")
    _err_console.print(f"data_root: [cyan]{cfg.data_root}[/cyan]")
    _err_console.print(f"venv:      [cyan]{_venv_root()}[/cyan]\n")

    # Build the new settings dict, starting from existing or all-defaults.
    base = dict(old_raw) if old_raw else Settings().model_dump()

    # 1. embedding provider
    new_settings = _step_embedding(base)

    # 2. vector / relation (single-option but exposed)
    new_settings["vector"] = {"provider": _step_choice(
        "vector provider", ["lancedb"], (base.get("vector") or {}).get("provider", "lancedb"),
    )}
    new_settings["relation"] = {"provider": _step_choice(
        "relation provider", ["sqlite"], (base.get("relation") or {}).get("provider", "sqlite"),
    )}

    # 3. server port
    server_block = base.get("server") or {}
    new_settings["server"] = {
        "port": IntPrompt.ask(
            "server port", default=int(server_block.get("port", 7788)),
            console=_err_console,
        ),
    }

    # Carry over other sections (ttl / search / recall) untouched.
    for key in ("ttl", "search", "recall"):
        if key in base:
            new_settings[key] = base[key]

    # 4. diff
    changed = diff_settings(old_raw or {}, new_settings) if old_raw else ["(initial)"]

    # If no fields changed AND it's not a first install, short-circuit.
    if old_raw is not None and not changed:
        _err_console.print("\n[dim]config unchanged — nothing to write[/dim]")
        return {
            "settings_changed": [],
            "wrote_settings": False,
            "ensured_dirs": False,
            "server": None,
            "alias": None,
            "first_install": False,
        }

    # 5. embedding probe (only if embedding section actually differs OR first install)
    embedding_changed = old_raw is None or new_settings.get("embedding") != (old_raw.get("embedding") or {})
    if embedding_changed:
        _step_probe_embedding(cfg, new_settings)

    # 6. write + ensure_dirs
    write_settings_atomic(cfg.settings_path, new_settings)
    cfg._settings = None  # type: ignore[attr-defined]
    cfg.ensure_dirs()

    # 7. server start/restart prompt
    server_payload = _step_server(cfg, old_raw is not None and bool(changed))

    # 8. symlink
    alias_result = _step_alias()

    return {
        "settings_changed": changed,
        "wrote_settings": True,
        "ensured_dirs": True,
        "server": server_payload,
        "alias": alias_result,
        "first_install": is_first_install,
    }


# ---------- step impls ----------

def _step_embedding(base: dict) -> dict:
    out = {k: v for k, v in base.items()}
    cur_emb = base.get("embedding") or {}
    cur_provider = cur_emb.get("provider")
    default_provider = cur_provider if cur_provider in ("local", "openai") else "openai"

    provider = Prompt.ask(
        "embedding provider",
        choices=["local", "openai"], default=default_provider,
        console=_err_console,
    )

    # Provider-specific defaults shouldn't bleed across providers.
    if cur_provider != provider:
        cur_emb = {}

    if provider == "openai":
        endpoint = Prompt.ask(
            "endpoint",
            default=cur_emb.get("endpoint") or "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            console=_err_console,
        )
        auth_env_key = Prompt.ask(
            "auth env var name",
            default=cur_emb.get("auth_env_key") or "QWEN_KEY",
            console=_err_console,
        )
        model = Prompt.ask(
            "model", default=cur_emb.get("model") or "text-embedding-v4",
            console=_err_console,
        )
        dim = IntPrompt.ask(
            "dim", default=int(cur_emb.get("dim") or 1024),
            console=_err_console,
        )
        out["embedding"] = {
            "provider": "openai", "endpoint": endpoint,
            "auth_env_key": auth_env_key, "model": model, "dim": dim,
            "timeout": cur_emb.get("timeout", 30.0),
        }
    else:
        model = Prompt.ask(
            "model", default=cur_emb.get("model") or "all-MiniLM-L6-v2",
            console=_err_console,
        )
        dim = IntPrompt.ask(
            "dim", default=int(cur_emb.get("dim") or 384),
            console=_err_console,
        )
        out["embedding"] = {
            "provider": "local", "model": model, "dim": dim,
            "endpoint": None, "auth_env_key": None,
            "timeout": cur_emb.get("timeout", 30.0),
        }
    return out


def _step_choice(label: str, choices: list[str], default: str) -> str:
    if len(choices) == 1:
        _err_console.print(f"[bold]{label}[/bold]: only `{choices[0]}` available")
        return choices[0]
    return Prompt.ask(label, choices=choices, default=default, console=_err_console)


def _step_probe_embedding(cfg: Config, new_settings: dict) -> None:
    cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
    while True:
        try:
            asyncio.run(validate_embedder(cfg))
            return
        except EmbedderValidationError as e:
            _err_console.print(f"[red]embedding probe failed:[/red] {e}")
            if not Confirm.ask("Re-edit embedding fields?", console=_err_console, default=True):
                sys.exit(1)
            new_settings.update(_step_embedding(new_settings))
            cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]


def _step_server(cfg: Config, settings_changed: bool) -> dict | None:
    is_running = False
    pid = 0
    if cfg.pid_path.exists():
        try:
            pid = int(cfg.pid_path.read_text().strip())
            is_running = pid_alive(pid)
        except ValueError:
            cfg.pid_path.unlink(missing_ok=True)

    if is_running and settings_changed:
        if not Confirm.ask(
            f"server is running (pid {pid}). settings changed — restart now?",
            console=_err_console, default=True,
        ):
            _err_console.print(
                "[yellow]warning:[/yellow] settings written but old server is still using old config. "
                "Run `memory-talk server stop && memory-talk server start` when ready."
            )
            return {"status": "running_stale", "pid": pid}
        stop_payload = stop_server_proc(cfg)
        _err_console.print(f"[dim]stopped pid {stop_payload.get('pid')}[/dim]")
        start_payload = start_server_proc(cfg)
        if start_payload.get("status") == "failed":
            emit_md_err(fmt_error(f"server failed to start: {start_payload.get('error')}"))
            return start_payload
        return {**start_payload, "restarted": True}

    if is_running and not settings_changed:
        return {"status": "running", "pid": pid}

    if Confirm.ask("start server now?", console=_err_console, default=True):
        start_payload = start_server_proc(cfg)
        if start_payload.get("status") == "failed":
            emit_md_err(fmt_error(f"server failed to start: {start_payload.get('error')}"))
        return start_payload
    return {"status": "not_started"}


def _step_alias() -> dict:
    """Create the `memory.talk → memory-talk` symlink in <venv>/bin/.
    No more install_mode branching — venv path is fixed."""
    target = _venv_memory_talk()
    if not target.exists():
        return {
            "status": "skipped_not_found",
            "message": f"{target} does not exist — bootstrap may have failed",
        }
    link_path = target.parent / "memory.talk"
    res = create_symlink(target, link_path)
    return {
        "status": res.status,
        "link_path": str(res.link_path),
        "target": str(res.target),
        "message": res.message,
    }


# ---------- summary ----------

def _summary_md(cfg: Config, result: dict) -> str:
    rows: list[tuple[str, str]] = []
    rows.append(("data_root", f"`{cfg.data_root}`"))
    rows.append(("settings", f"`{cfg.settings_path}`"))
    rows.append(("venv", f"`{_venv_root()}`"))

    s = cfg.settings
    rows.append(("embedding", _embedding_label(s.embedding)))
    rows.append(("vector", s.vector.provider))
    rows.append(("relation", s.relation.provider))
    rows.append(("port", str(s.server.port)))

    server = result.get("server")
    rows.append(("server", _server_label(server)))

    alias = result.get("alias") or {}
    rows.append(("alias", _alias_label(alias)))

    rows.append(("changed", _changed_label(result)))

    out = ["# setup · **ok**", "", "| field | value |", "|---|---|"]
    for k, v in rows:
        out.append(f"| {k} | {v} |")
    out.append("")
    return "\n".join(out)


def _embedding_label(emb) -> str:
    if emb.provider == "openai":
        return f"openai · {emb.model} · dim {emb.dim}"
    if emb.provider == "local":
        return f"local · {emb.model} · dim {emb.dim}"
    return f"{emb.provider} · dim {emb.dim}"


def _server_label(payload: dict | None) -> str:
    if payload is None:
        return "unchanged"
    status = payload.get("status", "?")
    if status == "started":
        suffix = " · restarted" if payload.get("restarted") else ""
        return f"started · pid {payload.get('pid')}{suffix}"
    if status == "running":
        return f"running · pid {payload.get('pid')} (no change)"
    if status == "running_stale":
        return f"running · pid {payload.get('pid')} (stale — needs restart)"
    if status == "already_running":
        return f"already_running · pid {payload.get('pid')}"
    if status == "not_started":
        return "not_started · run `memory-talk server start` to launch"
    if status == "failed":
        return f"failed (exit {payload.get('exit_code')}) — see stderr"
    return status


def _alias_label(alias: dict) -> str:
    status = alias.get("status", "")
    link = alias.get("link_path", "")
    target = alias.get("target", "")
    if status == "created":
        return f"`{link} → {Path(target).name}`"
    if status == "noop":
        return f"`{link}` (already points to `{Path(target).name}`)"
    if status == "overwrote":
        return f"`{link} → {Path(target).name}` (replaced)"
    if status == "skipped_other_target":
        return f"skipped — {link} points elsewhere"
    if status == "skipped_no_perm":
        return f"skipped (no write permission) — run manually: `ln -s {target} {link}`"
    if status == "skipped_regular_file":
        return f"skipped — `{link}` is a regular file"
    if status == "skipped_windows":
        return "skipped (windows — use a .bat or PowerShell alias instead)"
    if status == "skipped_not_found":
        return f"skipped — {alias.get('message', 'memory-talk not on PATH')}"
    return status


def _changed_label(result: dict) -> str:
    if result.get("first_install"):
        bits = ["settings.json (created)", "dirs"]
        server = result.get("server") or {}
        if server.get("status") == "started":
            bits.append("server started")
        return ", ".join(bits)
    if not result.get("wrote_settings"):
        return "nothing — config unchanged"
    bits = []
    fields = result.get("settings_changed") or []
    if fields:
        bits.append(humanize_paths(fields))
    server = result.get("server") or {}
    if server.get("restarted"):
        bits.append("server restarted")
    return ", ".join(bits) if bits else "nothing"
