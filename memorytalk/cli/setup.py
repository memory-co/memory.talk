"""CLI: setup — interactive idempotent install / configure / restart.

v3 simplifications vs v2:

- **No ``--data-root`` flag**; data root is fixed at ``~/.memory.talk``.
  Tests still honor ``MEMORY_TALK_DATA_ROOT`` env so they can run on a
  tmpdir without trampling the user's real install — that env var is an
  internal hook, not a user-facing knob.
- **No venv bootstrap / PATH takeover** — those are install-management
  concerns that should be handled by a package installer / dedicated
  ``memory.talk install`` command, not bundled with config.
- **No TTL / filter / explore prompts** — TTL is gone in v3; filter /
  explore are surfaced through their own commands (or not configured
  via setup at all).

What it still does:

1. Loads existing ``settings.json`` if any; diffs new vs old.
2. Prompts: embedding provider + model + dim (+ openai endpoint / key);
   vector provider; relation provider; server port.
3. Probes the embedding provider before writing (fail-fast).
4. Atomic write of ``settings.json``; ensure_dirs.
5. Offers to start the server (first install) or restart it (modify mode
   when the running server still has the old config).
"""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md, emit_md_err
from memorytalk.cli.server import (
    _server_responsive, pid_alive, start_server_proc, stop_server_proc,
)
from memorytalk.config import Config, ConfigValidationError, Settings
from memorytalk.util import console
from memorytalk.util.console import err_console, section
from memorytalk.util.settings_io import (
    diff_settings, read_settings_raw, write_settings_atomic,
)


_EMB_OPTIONS = [
    console.Option("local", description="sentence-transformers, runs locally on CPU/GPU"),
    console.Option("openai", description="OpenAI-compatible HTTP endpoint (DashScope / vLLM / OpenAI)"),
]


@click.command("setup")
def setup() -> None:
    """Interactive wizard: install / reconfigure / restart memory.talk."""
    cfg = Config()
    try:
        old_raw = read_settings_raw(cfg.settings_path)
    except ValueError:
        if not console.confirm(
            "settings.json is corrupted. Back it up to settings.json.bak and re-initialize?",
            default=True,
        ):
            sys.exit(1)
        bak = cfg.settings_path.with_suffix(".json.bak")
        cfg.settings_path.replace(bak)
        old_raw = None
        err_console.print(f"[dim]backed up corrupt settings → {bak}[/dim]")

    is_first_install = old_raw is None
    cfg.data_root.mkdir(parents=True, exist_ok=True)

    try:
        result = _wizard(cfg, old_raw, is_first_install)
    except KeyboardInterrupt:
        err_console.print("\n[dim]aborted by user — settings.json not written[/dim]")
        sys.exit(130)
    except ConfigValidationError as e:
        emit_md_err(fmt_error(str(e)))
        sys.exit(1)

    emit_md(_summary_md(cfg, result))


def _wizard(cfg: Config, old_raw: dict | None, is_first_install: bool) -> dict:
    """Returns a dict describing what the run did, for the summary."""
    mode = "首次安装" if is_first_install else "已有配置 — 修改模式"
    err_console.print(f"[bold]memory.talk setup[/bold] · {mode}")
    err_console.print(f"data_root: [cyan]{cfg.data_root}[/cyan]\n")

    # ``base`` is the raw existing settings.json — NOT a Settings model
    # dump. Mixing model defaults in would re-introduce the old bug
    # where wizard-untouched fields (search.ranking_formula etc.) got
    # materialized to disk and stopped tracking schema-default changes.
    base = dict(old_raw) if old_raw else {}

    # ── embedding ───────────────────────────────────────────────────────
    section("Embedding")
    # First-install pre-fill: recommended starting template (DashScope's
    # text-embedding-v4 over an OpenAI-compatible endpoint). The wizard
    # still prompts for every field — user can override anything before
    # the probe runs. We override emb_base here rather than the schema
    # default (EmbeddingConfig.provider="local") so that fresh Config()
    # calls without persisted settings still resolve to a local-only,
    # no-network, no-API-key state — important for tests and for the
    # "config went missing" recovery path.
    if is_first_install:
        emb_base = {
            "provider": "openai",
            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            "model": "text-embedding-v4",
            "dim": 1024,
        }
    else:
        emb_base = dict(base.get("embedding") or {})
    emb = _step_embedding(emb_base)

    # Probe the embedding before writing — fail-fast.
    err_console.print("[dim]probing embedding provider...[/dim]")
    _probe_embedding(emb)
    err_console.print("[green]✓ embedding verified[/green]")

    # ── storage ─────────────────────────────────────────────────────────
    section("Storage")
    vector_provider = _choice(
        "vector provider", ["lancedb"],
        (base.get("vector") or {}).get("provider", "lancedb"),
    )
    relation_provider = _choice(
        "relation provider", ["sqlite"],
        (base.get("relation") or {}).get("provider", "sqlite"),
    )

    # ── server ──────────────────────────────────────────────────────────
    section("Server")
    port_default = str(int((base.get("server") or {}).get("port", 7788)))
    port_str = console.text(
        "server port",
        default=port_default,
        validate=lambda v: (v.strip().isdigit() and 1 <= int(v) <= 65535)
        or "must be an integer in 1..65535",
    )

    # ── sync ────────────────────────────────────────────────────────────
    section("Sync")
    # Probe what'll auto-detect so the user can see ahead of time which
    # CLIs will be picked up. Endpoint discovery itself happens in the
    # SyncWatcher at server start — this is purely informational.
    _show_detected_endpoints()
    old_sync = base.get("sync") or {}
    enabled_default = old_sync.get("enabled", True if is_first_install else False)
    sync_enabled = console.confirm(
        "Enable backend sync? (auto-ingest Claude Code / Codex sessions etc.)",
        default=enabled_default,
    )

    # ── PATCH onto base ─────────────────────────────────────────────────
    # Setup writes ONLY the fields it actually prompted for. Anything
    # else the user had in settings.json — sync.debounce_ms, search.*,
    # recall.*, explore.*, embedding.batch_size, future fields — is
    # left untouched. This keeps "defaults that haven't been explicitly
    # overridden" tracking the Settings schema, so future default
    # changes (like the 0.8.2 ranking_formula -> "relevance") flow
    # through on next load without manual intervention.
    owned = {
        "server":   {"port": int(port_str)},
        "vector":   {"provider": vector_provider},
        "relation": {"provider": relation_provider},
        "embedding": emb,
        "sync":     {"enabled": sync_enabled},
    }
    new = _patch_owned(base, owned)

    # ── diff + persist ──────────────────────────────────────────────────
    diff = diff_settings(base, new)
    if not is_first_install and not diff:
        err_console.print("\n[dim]no field changed — nothing to write[/dim]")
        return {
            "changed": [], "diff": [],
            "settings_path": cfg.settings_path,
            "server_action": None,
            "embedding_dim_changed": False,
        }

    write_settings_atomic(cfg.settings_path, new)
    cfg._settings = None  # invalidate cached Settings
    cfg.ensure_dirs()

    # ── embedding dim change → would trigger reembed (deferred) ─────────
    old_dim = (base.get("embedding") or {}).get("dim")
    new_dim = emb.get("dim")
    dim_changed = (
        old_dim is not None
        and not is_first_install
        and old_dim != new_dim
    )

    # ── server start / restart ──────────────────────────────────────────
    server_action = _maybe_start_or_restart(cfg, is_first_install, bool(diff))

    return {
        "changed": diff,
        "diff": diff,
        "settings_path": cfg.settings_path,
        "server_action": server_action,
        "embedding_dim_changed": dim_changed,
    }


def _step_embedding(base: dict) -> dict:
    provider = _select("embedding provider", _EMB_OPTIONS,
                       default=base.get("provider", "local"))

    model_default = base.get("model") or (
        "all-MiniLM-L6-v2" if provider == "local" else "text-embedding-v4"
    )
    model = console.text("model", default=model_default)
    dim = int(console.text(
        "vector dim",
        default=str(int(base.get("dim", 384 if provider == "local" else 1024))),
        validate=lambda v: v.strip().isdigit() or "must be a positive integer",
    ))

    out: dict = {"provider": provider, "model": model, "dim": dim}
    if provider == "openai":
        out["endpoint"] = console.text(
            "endpoint", default=base.get("endpoint") or "",
            validate=lambda v: bool(v.strip()) or "endpoint required",
        )
        out["auth_key"] = console.text(
            "auth_key (literal value or ${VAR})",
            default=base.get("auth_key") or "",
            validate=lambda v: bool(v.strip()) or "auth_key required",
        )
        out["timeout"] = base.get("timeout", 30.0)
    return out


def _patch_owned(base: dict, owned: dict[str, dict]) -> dict:
    """Apply ``owned`` updates onto ``base`` at field-level granularity.

    For each section in ``owned``:
      - Merge ``owned[section]`` keys into ``base[section]`` (creating
        the section if missing).
      - Keys that are in ``base[section]`` but NOT in ``owned[section]``
        are preserved as-is.

    Sections that aren't in ``owned`` at all (e.g. ``search``, ``recall``,
    ``explore``, ``index``) are returned untouched.

    Provider switch (openai → local) note: stale provider-specific
    keys like ``endpoint`` / ``auth_key`` survive in the file. They're
    inert when ``provider != "openai"`` (Settings just ignores them on
    load). Strict patch — wizard owns what wizard prompted for; it
    doesn't synthesize cleanup of unrelated keys.
    """
    new = dict(base)
    for section, fields in owned.items():
        section_data = dict(new.get(section, {}))
        section_data.update(fields)
        new[section] = section_data
    return new


def _show_detected_endpoints() -> None:
    """List adapters whose ``DEFAULT_LOCATION`` exists on the user's
    machine — those will be auto-attached on server start. Adapters
    without a default location (e.g. openclaw) need explicit
    ``settings.sync.endpoints`` to participate; we don't surface them
    here because the wizard doesn't (yet) collect remote-endpoint config.
    """
    from pathlib import Path
    from memorytalk.adapters import ADAPTERS
    detected = []
    missing = []
    for name, cls in ADAPTERS.items():
        loc = getattr(cls, "DEFAULT_LOCATION", None)
        if not loc:
            continue
        if Path(loc).expanduser().exists():
            detected.append((name, loc))
        else:
            missing.append((name, loc))
    if detected:
        err_console.print("[dim]Detected sources:[/dim]")
        for name, loc in detected:
            err_console.print(f"  [green]✓[/green] {name} → [cyan]{loc}[/cyan]")
    if missing:
        err_console.print("[dim]Not present (will be ignored):[/dim]")
        for name, loc in missing:
            err_console.print(f"  [dim]·[/dim] {name} → [dim]{loc}[/dim]")
    if not detected and not missing:
        err_console.print("[dim](no sync adapters with default locations are registered)[/dim]")


def _probe_embedding(emb_block: dict) -> None:
    """Run the async probe synchronously (wizard is sync)."""
    import asyncio
    # Build a synthetic Config with these embedding settings.
    synth = Config()
    synth._settings = Settings(**{
        **Settings().model_dump(),
        "embedding": emb_block,
    })
    from memorytalk.provider.embedding import EmbedderValidationError, validate_embedder
    try:
        asyncio.run(validate_embedder(synth))
    except EmbedderValidationError as e:
        raise ConfigValidationError(f"embedding probe failed: {e}") from e


def _maybe_start_or_restart(
    cfg: Config, is_first_install: bool, has_diff: bool,
) -> str | None:
    """Returns a short string describing the action taken, or None."""
    # Same guard as start_server_proc: pid_alive alone is fooled by a
    # recycled PID, so verify the daemon actually answers HTTP before we
    # consider "restart" — otherwise stop_server_proc would SIGTERM an
    # unrelated process that happens to hold the stale PID.
    pid_alive_now = (
        cfg.pid_path.exists()
        and pid_alive(int(cfg.pid_path.read_text()))
        and _server_responsive(cfg)
    )

    if is_first_install:
        if console.confirm("Start the server now?", default=True):
            r = start_server_proc(cfg)
            return f"started · pid {r['pid']} · port {r['port']}" if r["status"] == "started" \
                else r.get("status", "?")
        return None

    if has_diff and pid_alive_now:
        if console.confirm(
            "Server is running with the old config. Restart now?", default=True,
        ):
            stop_server_proc(cfg)
            r = start_server_proc(cfg)
            return f"restarted · pid {r['pid']} · port {r['port']}" if r["status"] == "started" \
                else r.get("status", "?")
        return None

    return None


def _summary_md(cfg: Config, result: dict) -> str:
    lines = ["# setup · **ok**", "", "| field | value |", "|---|---|"]
    lines.append(f"| data_root | `{cfg.data_root}` |")
    lines.append(f"| settings | `{result['settings_path']}` |")
    if not result["changed"]:
        lines.append("| changed | nothing — config unchanged |")
    else:
        diff_pretty = ", ".join(result["changed"][:6])
        if len(result["changed"]) > 6:
            diff_pretty += f", +{len(result['changed']) - 6} more"
        lines.append(f"| changed | {len(result['changed'])} fields ({diff_pretty}) |")
    if result["server_action"]:
        lines.append(f"| server | {result['server_action']} |")
    else:
        lines.append("| server | (unchanged) |")
    if result["embedding_dim_changed"]:
        lines.append("| notice | **embedding dim changed** — re-embed all cards via `memory.talk setup` once card writes are implemented |")
    return "\n".join(lines) + "\n"


# ────────── thin questionary wrappers ──────────

def _select(label, options, default):
    return console.select(label, options, default=default)


def _choice(label, choices: list[str], default: str) -> str:
    return console.select(
        label,
        [console.Option(c) for c in choices],
        default=default,
    )
