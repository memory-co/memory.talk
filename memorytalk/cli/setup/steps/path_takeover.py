"""Wizard step: redirect every `memory-talk` on $PATH to the chosen target.

Why
---
After a dedicated-venv bootstrap, the user's shell still resolves
`memory-talk` to whatever was on PATH first (commonly a brew-installed
or pipx-installed entry-point script — the same one they used to invoke
`memory-talk setup`). Without intervention the freshly bootstrapped venv
is unreachable from the user's shell and the whole "isolation" point is
defeated.

Rather than fighting PATH ordering by installing a higher-priority
shim, this step **finds every `memory-talk` already on $PATH and
replaces them all with symlinks** pointing at the chosen target. Any
PATH entry the user currently relies on keeps working — it just
resolves to the canonical binary now.

Decision rules per discovered path
----------------------------------
- already resolves to target (incl. is the target itself) → noop
- symlink to elsewhere                                    → unlink + relink
- regular file (typically a pip-generated entry-point)    → mv to ``<name>.bak``
                                                            then symlink
- no write permission                                     → skip + manual hint

A single confirm covers all changes (with the full list shown first) so
the user isn't tapping Enter N times. ``.bak`` files preserve a
trivially reversible escape hatch — `mv X.bak X` restores the original.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

from .. import _prompt
from .._io import err_console, section


def _find_all_on_path(name: str) -> list[Path]:
    """Every `name` file or symlink reachable through $PATH (in PATH order, dedup'd)."""
    seen: set[str] = set()
    found: list[Path] = []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or d in seen:
            continue
        seen.add(d)
        candidate = Path(d) / name
        try:
            if candidate.is_symlink() or candidate.exists():
                found.append(candidate)
        except OSError:
            pass
    return found


def _resolve_safe(p: Path) -> Path | None:
    try:
        return p.resolve()
    except OSError:
        return None


def _classify(path: Path, target_resolved: Path | None) -> str:
    """ok | symlink | file"""
    p_resolved = _resolve_safe(path)
    if p_resolved is not None and target_resolved is not None and p_resolved == target_resolved:
        return "ok"
    return "symlink" if path.is_symlink() else "file"


def _step_path_takeover(target: Path) -> dict:
    """Make every memory-talk on $PATH point at ``target``.

    Returns ``{"target": str, "actions": [{path, status, ...}]}``. Statuses:
    ``ok``, ``redirected``, ``replaced``, ``skipped``, ``no_perm``,
    ``windows``, ``not_found``.
    """
    if sys.platform == "win32":
        return {"target": str(target), "actions": [
            {"path": "(all)", "status": "windows",
             "message": "symlinks need admin/dev mode; skipped"},
        ]}

    section("PATH takeover")
    target_resolved = _resolve_safe(target)
    paths = _find_all_on_path("memory-talk")

    if not paths:
        # User invoked setup via an absolute path or via a PATH entry that
        # was somehow wiped — surface this as a soft warning rather than
        # silently doing nothing. Target stays at <chosen-venv>/bin/.
        err_console.print(
            f"[yellow]note:[/yellow] no `memory-talk` found on $PATH. "
            f"Add `{target.parent}` to your PATH to make it reachable."
        )
        return {"target": str(target), "actions": [
            {"path": "(none)", "status": "not_found",
             "message": "no memory-talk on $PATH"},
        ]}

    already_ok: list[Path] = []
    needs_redirect: list[tuple[Path, str]] = []  # (path, kind) where kind in {symlink, file}
    for p in paths:
        kind = _classify(p, target_resolved)
        if kind == "ok":
            already_ok.append(p)
        else:
            needs_redirect.append((p, kind))

    actions: list[dict] = [
        {"path": str(p), "status": "ok", "message": "already → target"}
        for p in already_ok
    ]

    if not needs_redirect:
        return {"target": str(target), "actions": actions}

    # Show the plan, then a single confirm.
    err_console.print(
        f"found [bold]{len(paths)}[/bold] `memory-talk` on $PATH "
        f"(target: [cyan]{target}[/cyan]):"
    )
    for p, kind in needs_redirect:
        if kind == "symlink":
            cur = _resolve_safe(p) or "?"
            err_console.print(f"  · {p} [dim]symlink → {cur}[/dim]")
        else:
            err_console.print(f"  · {p} [dim]regular file (pip-installed)[/dim]")
    for p in already_ok:
        err_console.print(f"  · {p} [green](already correct)[/green]")

    if not _prompt.confirm(
        f"Redirect {len(needs_redirect)} path(s) above to → {target}?\n"
        "  · symlinks recreated\n"
        "  · regular files backed up as <name>.bak before being replaced",
        default=True,
    ):
        actions.extend(
            {"path": str(p), "status": "skipped", "message": "user declined"}
            for p, _ in needs_redirect
        )
        return {"target": str(target), "actions": actions}

    # Apply each change immediately and emit per-action feedback so the
    # user sees the takeover land in real time (not buried in the final
    # summary, which they may never see if they Ctrl-C the wizard).
    n_redirected = 0
    n_replaced = 0
    n_failed = 0
    for p, kind in needs_redirect:
        action = _redirect_one(p, target, kind)
        actions.append(action)
        status = action["status"]
        if status == "redirected":
            err_console.print(
                f"  [green]✓[/green] {p} [dim]→ symlink updated → {target}[/dim]"
            )
            n_redirected += 1
        elif status == "replaced":
            err_console.print(
                f"  [green]✓[/green] {p} [dim]→ backup as {Path(action['backup']).name}; "
                f"symlink → {target}[/dim]"
            )
            n_replaced += 1
        else:  # no_perm
            err_console.print(
                f"  [red]✗[/red] {p}: {action.get('message', 'failed')}"
            )
            n_failed += 1

    bits: list[str] = []
    if n_replaced:
        bits.append(f"{n_replaced} file replaced")
    if n_redirected:
        bits.append(f"{n_redirected} symlink redirected")
    if n_failed:
        bits.append(f"[red]{n_failed} failed[/red]")
    err_console.print(f"\n[bold]PATH takeover[/bold] · " + ", ".join(bits))
    return {"target": str(target), "actions": actions}


def _redirect_one(path: Path, target: Path, kind: str) -> dict:
    if kind == "symlink":
        try:
            path.unlink()
            os.symlink(target, path)
            return {"path": str(path), "status": "redirected"}
        except PermissionError as e:
            return {"path": str(path), "status": "no_perm", "message": str(e)}
        except OSError as e:
            return {"path": str(path), "status": "no_perm", "message": str(e)}

    # kind == "file"
    bak = Path(str(path) + ".bak")
    try:
        path.rename(bak)
    except PermissionError as e:
        return {"path": str(path), "status": "no_perm", "message": str(e)}
    try:
        os.symlink(target, path)
    except OSError as e:
        # restore the original on failure
        try:
            bak.rename(path)
        except OSError:
            pass
        return {"path": str(path), "status": "no_perm", "message": str(e)}
    return {"path": str(path), "status": "replaced", "backup": str(bak)}
