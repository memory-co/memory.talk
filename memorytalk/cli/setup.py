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

**Wizard shape: flat list of steps, no early returns.** The wizard
iterates ``STEPS`` and runs every entry exactly once. Each step is
idempotent and decides for itself whether to act. There is intentionally
no "if no diff, return early" path through the middle of the wizard —
that pattern repeatedly caused new bottom-of-wizard steps to get
silently skipped on re-runs where settings.json was untouched. Adding a
new step = appending one entry to ``STEPS``; it cannot be bypassed.
"""
from __future__ import annotations
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import click

from memorytalk.cli._format import fmt_error
from memorytalk.cli._render import emit_md, emit_md_err
from memorytalk.cli.server import (
    _server_responsive, pid_alive, start_server_proc, stop_server_proc,
)
from memorytalk.config import Config, ConfigValidationError, Settings
from memorytalk.hooks import ADAPTERS, HostState
from memorytalk.hooks import materialize as hook_materialize
from memorytalk.hooks import probe as hook_probe
from memorytalk.hooks import state as hook_state
from memorytalk.util import console
from memorytalk.util.console import CheckOption, err_console, section
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


# ──────────────────────────── pipeline ────────────────────────────────

@dataclass
class Ctx:
    """Mutable context threaded through every step.

    ``owned`` accumulates input collected by ``_run_*`` steps and is
    persisted by the ``persist`` step. ``new`` / ``diff`` / ``written``
    are populated by ``persist`` for downstream steps to read.
    """
    cfg: Config
    base: dict
    is_first_install: bool
    owned: dict = field(default_factory=dict)
    new: dict | None = None
    diff: list[str] = field(default_factory=list)
    written: bool = False


@dataclass(frozen=True)
class Step:
    """One pipeline entry. ``section`` is the banner to print before
    ``run``; ``None`` means no banner."""
    name: str
    section: str | None
    run: Callable[[Ctx], dict]


def _wizard(cfg: Config, old_raw: dict | None, is_first_install: bool) -> dict:
    """Run every step in ``STEPS`` exactly once and build the summary.

    Do NOT add early returns / mid-pipeline shortcuts here. Each step
    owns its own "is there anything to do?" check and is idempotent.
    """
    mode = "首次安装" if is_first_install else "已有配置 — 修改模式"
    err_console.print(f"[bold]memory.talk setup[/bold] · {mode}")
    err_console.print(f"data_root: [cyan]{cfg.data_root}[/cyan]\n")

    # ``base`` is the raw existing settings.json — NOT a Settings model
    # dump. Mixing model defaults in would re-introduce the old bug
    # where wizard-untouched fields (search.ranking_formula etc.) got
    # materialized to disk and stopped tracking schema-default changes.
    ctx = Ctx(
        cfg=cfg,
        base=dict(old_raw) if old_raw else {},
        is_first_install=is_first_install,
    )

    results: dict[str, dict] = {}
    for step in STEPS:
        if step.section is not None:
            section(step.section)
        results[step.name] = step.run(ctx)

    return _build_result(ctx, results)


# ─────────────────────── individual step bodies ──────────────────────

def _run_embedding(ctx: Ctx) -> dict:
    """Prompt for embedding config, probe it (fail-fast), stash in owned."""
    # First-install pre-fill: recommended starting template (DashScope's
    # text-embedding-v4 over an OpenAI-compatible endpoint). The wizard
    # still prompts for every field. We override emb_base here rather
    # than the schema default (EmbeddingConfig.provider="local") so that
    # fresh Config() calls without persisted settings still resolve to a
    # local-only, no-network, no-API-key state — important for tests and
    # for the "config went missing" recovery path.
    if ctx.is_first_install:
        emb_base = {
            "provider": "openai",
            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            "model": "text-embedding-v4",
            "dim": 1024,
        }
    else:
        emb_base = dict(ctx.base.get("embedding") or {})
    emb = _collect_embedding(emb_base)

    err_console.print("[dim]probing embedding provider...[/dim]")
    _probe_embedding(emb)
    err_console.print("[green]✓ embedding verified[/green]")

    ctx.owned["embedding"] = emb
    return {"emb": emb}


def _run_storage(ctx: Ctx) -> dict:
    vector_provider = _choice(
        "vector provider", ["lancedb"],
        (ctx.base.get("vector") or {}).get("provider", "lancedb"),
    )
    relation_provider = _choice(
        "relation provider", ["sqlite"],
        (ctx.base.get("relation") or {}).get("provider", "sqlite"),
    )
    ctx.owned["vector"] = {"provider": vector_provider}
    ctx.owned["relation"] = {"provider": relation_provider}
    return {"vector": vector_provider, "relation": relation_provider}


def _run_server_config(ctx: Ctx) -> dict:
    port_default = str(int((ctx.base.get("server") or {}).get("port", 7788)))
    port_str = console.text(
        "server port",
        default=port_default,
        validate=lambda v: (v.strip().isdigit() and 1 <= int(v) <= 65535)
        or "must be an integer in 1..65535",
    )
    ctx.owned["server"] = {"port": int(port_str)}
    return {"port": int(port_str)}


def _run_sync(ctx: Ctx) -> dict:
    # Probe what'll auto-detect so the user can see ahead of time which
    # CLIs will be picked up. Endpoint discovery itself happens in the
    # SyncWatcher at server start — this is purely informational.
    _show_detected_endpoints()
    old_sync = ctx.base.get("sync") or {}
    enabled_default = old_sync.get(
        "enabled", True if ctx.is_first_install else False,
    )
    sync_enabled = console.confirm(
        "Enable backend sync? (auto-ingest Claude Code / Codex sessions etc.)",
        default=enabled_default,
    )
    ctx.owned["sync"] = {"enabled": sync_enabled}
    return {"enabled": sync_enabled}


def _run_persist(ctx: Ctx) -> dict:
    """Diff owned fields against existing settings.json and write iff diff.

    Setup writes ONLY the fields it actually prompted for. Anything else
    the user had in settings.json — sync.debounce_ms, search.*, recall.*,
    explore.*, embedding.batch_size, future fields — is left untouched.
    This keeps "defaults that haven't been explicitly overridden"
    tracking the Settings schema, so future default changes (like the
    0.8.2 ranking_formula -> "relevance") flow through on next load
    without manual intervention.
    """
    ctx.new = _patch_owned(ctx.base, ctx.owned)
    ctx.diff = diff_settings(ctx.base, ctx.new)
    if ctx.diff:
        write_settings_atomic(ctx.cfg.settings_path, ctx.new)
        ctx.cfg._settings = None  # invalidate cached Settings
        ctx.written = True
    else:
        err_console.print("\n[dim]settings.json unchanged[/dim]")
    ctx.cfg.ensure_dirs()
    return {"wrote": ctx.written, "diff": ctx.diff}


def _run_server_proc(ctx: Ctx) -> dict:
    """Start the daemon (first install) or offer restart (config drift)."""
    return {"action": _maybe_start_or_restart(
        ctx.cfg, ctx.is_first_install, bool(ctx.diff),
    )}


def _run_hooks(ctx: Ctx) -> dict:
    """Multi-select prompt: install / keep / remove memory.talk's recall
    hook in each detected host AI CLI (Claude Code, Codex, …)."""
    return _step_install_hooks(ctx.cfg)


# ──────────────────────────── step registry ───────────────────────────

STEPS: tuple[Step, ...] = (
    Step("embedding",     "Embedding",     _run_embedding),
    Step("storage",       "Storage",       _run_storage),
    Step("server_config", "Server",        _run_server_config),
    Step("sync",          "Sync",          _run_sync),
    Step("persist",       None,            _run_persist),
    Step("server_proc",   None,            _run_server_proc),
    Step("hooks",         "Recall hooks",  _run_hooks),
)


def _build_result(ctx: Ctx, results: dict[str, dict]) -> dict:
    """Translate per-step results into the dict ``_summary_md`` expects."""
    # Embedding dim change → would trigger reembed (deferred). Derived
    # from base vs owned rather than tracked in a step because it's
    # purely informational and doesn't fan out into another action.
    old_dim = (ctx.base.get("embedding") or {}).get("dim")
    new_emb = ctx.owned.get("embedding") or {}
    new_dim = new_emb.get("dim")
    dim_changed = (
        old_dim is not None
        and not ctx.is_first_install
        and old_dim != new_dim
    )

    return {
        "changed": ctx.diff,
        "diff": ctx.diff,
        "settings_path": ctx.cfg.settings_path,
        "server_action": results.get("server_proc", {}).get("action"),
        "embedding_dim_changed": dim_changed,
        "hooks": results.get("hooks") or {},
    }


# ────────────────────────── input collectors ──────────────────────────

def _collect_embedding(base: dict) -> dict:
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


# ────────────────────────── hook install step ─────────────────────────

def _step_install_hooks(cfg: Config) -> dict:
    """Idempotent: re-run shows current state inline and ``Enter`` on
    the default selection (all detected hosts checked) holds state for
    already-installed hosts and installs missing ones.

    Returns a summary dict consumed by ``_summary_md``.
    """
    # Hook install is interactive-only: it shows a multi-select and can
    # block on the Codex trust dialog. Non-TTY runs (tests, piped input,
    # CI) silently skip so they don't surprise the user with side effects.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return {"skipped": "non-interactive shell"}

    if not shutil.which("memory.talk"):
        err_console.print(
            "[yellow]⚠ `memory.talk` is not on PATH — skipping hook installation.[/]\n"
            "  The hook command is `memory.talk recall --hook`; it must resolve\n"
            "  when AI CLIs spawn it. Reinstall via `pipx install memorytalk`\n"
            "  (or another method that puts the script on PATH), then re-run setup."
        )
        return {"skipped": "memory.talk not in PATH"}

    rows: list[HookRow] = []
    for adapter in ADAPTERS:
        presence = adapter.detect()
        mdir = hook_materialize.materialized_dir(cfg.data_root, adapter.asset_subdir)
        state = (
            adapter.current_state(mdir) if presence is not None
            else HostState.ABSENT
        )
        rows.append(HookRow(
            adapter=adapter, presence=presence, state=state, materialized=mdir,
        ))

    if not any(r.presence for r in rows):
        err_console.print(
            "[dim]No supported AI CLIs detected on PATH. Install one of:[/dim]"
        )
        for r in rows:
            err_console.print(f"  [dim]·[/dim] {r.adapter.display_name}")
        return {"hosts": []}

    options = [
        CheckOption(
            value=r.adapter.name,
            title=_format_option_title(r, cfg),
            checked=r.presence is not None,
            disabled="not found in PATH" if r.presence is None else None,
        )
        for r in rows
    ]

    selected = set(console.checkbox(
        "Toggle host integrations (space to flip, enter to apply):",
        options,
    ))

    summary_hosts: list[dict] = []
    for r in rows:
        if r.presence is None:
            continue
        wanted = r.adapter.name in selected
        installed_now = r.state != HostState.ABSENT
        if wanted:
            summary_hosts.append(_apply_install(r, cfg))
        elif installed_now:
            summary_hosts.append(_apply_uninstall(r, cfg))
        else:
            summary_hosts.append({
                "host": r.adapter.name, "action": "skip", "state": "absent",
            })
    return {"hosts": summary_hosts}


class HookRow:
    """Internal row state for the hooks step."""
    __slots__ = ("adapter", "presence", "state", "materialized")

    def __init__(self, adapter, presence, state, materialized):
        self.adapter = adapter
        self.presence = presence
        self.state = state
        self.materialized = materialized


def _format_option_title(r: HookRow, cfg: Config) -> str:
    name = f"{r.adapter.display_name}"
    if r.presence is None:
        return f"{name:14}  (not found in PATH)"
    ver = r.presence.version or "?"
    tag = _state_tag(r, cfg)
    return f"{name:14}  v{ver:<10}  {tag}"


def _state_tag(r: HookRow, cfg: Config) -> str:
    s = r.state
    if s is HostState.ABSENT:
        return "absent — will install"
    if s is HostState.INSTALLED:
        ts = hook_state.last_verified(cfg.data_root, r.adapter.name)
        suffix = f" (probed {ts})" if ts else ""
        return f"installed{suffix}"
    if s is HostState.INSTALLED_VERIFIED:
        return "installed-verified"
    if s is HostState.INSTALLED_DRIFT:
        return "installed but bundle changed — will re-materialize"
    if s is HostState.INSTALLED_DISABLED:
        return "installed but disabled — will re-enable"
    if s is HostState.INSTALLED_FAILED:
        return "[red]install failed — manual fix needed[/red]"
    if s is HostState.INSTALLED_UNTRUSTED:
        return "[yellow]installed, awaiting trust in host TUI[/yellow]"
    return str(s.value)


def _apply_install(r: HookRow, cfg: Config) -> dict:
    adapter = r.adapter
    if r.state is HostState.INSTALLED_FAILED:
        err_console.print(
            f"[red]✘ {adapter.display_name}: in failed state — "
            f"run `{adapter.name} plugin list` and resolve manually.[/red]"
        )
        return {"host": adapter.name, "action": "skip", "state": "failed"}

    err_console.print(f"\n▸ {adapter.display_name}")

    # Materialize the bundled assets onto disk. Returns True if it
    # actually wrote — false means hash matched, no I/O.
    changed = hook_materialize.materialize(adapter.asset_subdir, r.materialized)
    if changed:
        err_console.print(f"  [green]✓[/green] assets materialized → {r.materialized}")
    else:
        err_console.print(f"  [dim]·[/dim] assets up to date")

    try:
        adapter.install(r.materialized)
    except RuntimeError as e:
        err_console.print(f"  [red]✘ install failed:[/red] {e}")
        return {"host": adapter.name, "action": "install-failed", "error": str(e)}
    err_console.print(f"  [green]✓[/green] plugin installed")

    if adapter.needs_trust and not adapter.trust_ok():
        if not _wait_for_trust(adapter):
            return {
                "host": adapter.name, "action": "trust-required",
                "state": "installed-untrusted",
            }

    if not _verify(r, cfg):
        err_console.print(
            f"  [yellow]⚠ probe did not detect the hook firing.[/yellow]\n"
            f"  [dim]The plugin is installed but verification failed — try a real "
            f"prompt in {adapter.display_name} manually.[/dim]"
        )
        return {"host": adapter.name, "action": "installed-unverified"}

    err_console.print(f"  [green]✓[/green] verified end-to-end")
    return {"host": adapter.name, "action": "verified"}


def _apply_uninstall(r: HookRow, cfg: Config) -> dict:
    adapter = r.adapter
    err_console.print(f"\n▸ {adapter.display_name} — uninstalling")
    try:
        adapter.uninstall()
    except RuntimeError as e:
        err_console.print(f"  [red]✘ uninstall failed:[/red] {e}")
        return {"host": adapter.name, "action": "uninstall-failed", "error": str(e)}
    if r.materialized.exists():
        shutil.rmtree(r.materialized, ignore_errors=True)
    hook_state.clear(cfg.data_root, adapter.name)
    err_console.print(f"  [green]✓[/green] removed plugin, marketplace, and assets")
    return {"host": adapter.name, "action": "uninstalled"}


def _wait_for_trust(adapter) -> bool:
    """Block on user completing one-time trust in host's TUI (Codex).
    Non-interactive shells exit early with a warning — CI must re-run
    interactively to finish trust."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        err_console.print(
            f"  [yellow]⚠ {adapter.display_name} requires one-time trust via its TUI.[/yellow]\n"
            f"  [dim]Re-run `memory.talk setup` interactively to complete this step.[/dim]"
        )
        return False
    err_console.print(
        f"\n  [yellow]⚠ {adapter.display_name} requires one-time trust:[/yellow]\n"
        f"    1. Open a new terminal and run:  [cyan]codex[/cyan]\n"
        f"    2. Wait for the [bold]Hooks need review[/bold] dialog\n"
        f"       (or type [cyan]/hooks[/cyan] inside the TUI)\n"
        f"    3. Press [bold]2[/bold] (Trust all and continue)\n"
        f"    4. ESC to exit the TUI"
    )
    try:
        input("\n  Press Enter when done (Ctrl-C to abort this host): ")
    except (KeyboardInterrupt, EOFError):
        err_console.print("  [dim]skipped[/dim]")
        return False
    if adapter.trust_ok():
        err_console.print("  [green]✓[/green] trust detected")
        return True
    err_console.print(
        "  [red]✘ trust state not found in ~/.codex/config.toml — "
        "re-run setup after pressing 't' in the TUI.[/red]"
    )
    return False


def _verify(r: HookRow, cfg: Config) -> bool:
    token = hook_probe.new_token()
    argv = r.adapter.probe_command(token)
    if hook_probe.run_probe(argv):
        hook_state.record_verified(
            cfg.data_root, r.adapter.name,
            hook_materialize.bundled_hash(r.adapter.asset_subdir),
        )
        return True
    return False


# ──────────────────────────── helpers ─────────────────────────────────

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
    for sect, fields in owned.items():
        section_data = dict(new.get(sect, {}))
        section_data.update(fields)
        new[sect] = section_data
    return new


def _show_detected_endpoints() -> None:
    """List adapters whose ``DEFAULT_LOCATION`` exists on the user's
    machine — those will be auto-attached on server start. Adapters
    without a default location (e.g. openclaw) need explicit
    ``settings.sync.endpoints`` to participate; we don't surface them
    here because the wizard doesn't (yet) collect remote-endpoint config.
    """
    from memorytalk.adapters import ADAPTERS as SYNC_ADAPTERS
    detected = []
    missing = []
    for name, cls in SYNC_ADAPTERS.items():
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
    hooks = result.get("hooks") or {}
    if "skipped" in hooks:
        lines.append(f"| hooks | skipped — {hooks['skipped']} |")
    elif hooks.get("hosts"):
        host_strs = [f"{h['host']}={h['action']}" for h in hooks["hosts"]]
        lines.append(f"| hooks | {', '.join(host_strs)} |")
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
