# Claude Code UserPromptSubmit Hook (memory.talk recall integration)

**Date:** 2026-05-01
**Scope:** new wizard step at the end of `memory-talk setup`; `--hook` mode added to existing `memory-talk recall` CLI; new install logic for `~/.claude/settings.json`.
**Status:** Approved (brainstorming session 2026-05-01).

## Why

Today, memory.talk is "wired into Claude Code" only when installed via the Claude Code plugin marketplace (the existing `hooks/hooks.json` references `${CLAUDE_PLUGIN_ROOT}` which is set only by Claude's plugin runtime). Users who install memory.talk through `pip install` + `memory-talk setup` get no hook integration at all.

This spec adds a setup step that, after the server is running, detects Claude Code on the user's machine and installs a `UserPromptSubmit` hook directly into `~/.claude/settings.json`. The hook calls memory.talk's recall API on every user prompt and feeds the recalled memories back to Claude as `additionalContext`.

## What changes

### 1. `recall` CLI gains a `--hook` mode

`memory-talk recall <session_id> <prompt>` continues to work for ad-hoc CLI calls. A new flag `--hook` switches the I/O contract:

- **stdin**: full JSON payload from Claude Code's UserPromptSubmit event. Hook extracts `session_id` and `prompt` fields. Positional args, if passed, are ignored in this mode.
- **HTTP**: same `POST /v2/recall` to the local server (no logic change).
- **stdout**: a single JSON object Claude expects for hook injection:

  ```json
  {
    "hookSpecificOutput": {
      "hookEventName": "UserPromptSubmit",
      "additionalContext": "Recalled from prior sessions:\n\n- [card_xxxx] summary one\n- [card_yyyy] summary two"
    }
  }
  ```

- **failure mode**: any error (stdin parse, missing fields, server down, server 4xx/5xx, network timeout) → emit JSON with `additionalContext: ""` and `exit 0`. Never block the user prompt. stderr may carry diagnostics.
- **timeout**: HTTP timeout = 2.0s. Short on purpose — if the server is down, the hook returns empty quickly so Claude doesn't stall.
- **empty recall**: when `recalled` is empty, `additionalContext` is the empty string (no "no memories found" placeholder, to keep Claude's context clean).
- **session_id**: passed through to recall API verbatim. No mapping between Claude session ID and memory-talk session ID is introduced — recall service already accepts arbitrary session IDs (lazy semantics).

### 2. New wizard step: `_step_claude_hook`

Runs as the final wizard step, immediately after server start/restart. Its job is to write a UserPromptSubmit entry into `~/.claude/settings.json`.

#### Detection (gate)

Both must be true:
- `~/.claude/` directory exists
- `claude` binary resolves on `$PATH` (via `shutil.which`)

If either is missing → step soft-skips. The summary table reports `claude hook | skipped`. No prompt, no error.

#### Install / merge logic

When the gate passes:
1. Read `~/.claude/settings.json`. If missing → treat as `{}`. If JSON-corrupt → soft-skip with a yellow warning (don't try to repair); summary reports `claude hook | skipped (settings.json corrupt)`.
2. Walk `data["hooks"]["UserPromptSubmit"]` (creating the empty array path if absent). Search the inner `hooks: [...]` arrays for any entry whose `_source == "memory-talk"`.
3. Build the canonical entry:

   ```json
   {
     "type": "command",
     "command": "memory-talk recall --hook",
     "async": false,
     "_source": "memory-talk"
   }
   ```

4. Apply one of three actions:
   - **not found** → append a new outer block `{"hooks": [<entry>]}` to `UserPromptSubmit`. Summary: `claude hook | installed`.
   - **found, command identical** → noop. Summary: `claude hook | unchanged`.
   - **found, command differs** → replace that entry's `command` (and any other diff'ed canonical fields) in place; preserve any unknown sibling fields the user may have added. Summary: `claude hook | updated`.

5. Atomic write back via the same temp-file + rename pattern used by `util/settings_io.write_settings_atomic`. **Never touch other event types or other hooks.** Only the matching `_source: "memory-talk"` entry is mutated.

6. If the write fails (PermissionError, disk full, etc.) → soft-skip with a yellow warning; summary reports `claude hook | skipped (write failed)`. The wizard does not abort.

#### Idempotency tag

The marker `"_source": "memory-talk"` is non-spec'd by Claude Code. Per Claude's behavior documentation, unknown fields in hook entries are preserved/ignored. We use this tag because:
- It distinguishes our entry from any UserPromptSubmit hooks the user installed manually or via other tools.
- It survives reformatting / merging / re-running setup.
- A user who deletes the `_source` field deliberately has opted out of automatic management; we'll leave their entry alone and append a new one (acceptable: they made the choice).

### 3. Summary table row

The wizard's final markdown summary gains a `claude hook` row, positioned between the existing `PATH takeover` and `changed` rows.

Possible values:

| value | meaning |
|---|---|
| `installed` | new entry appended |
| `updated` | existing entry's command was refreshed |
| `unchanged` | existing entry already correct |
| `skipped (Claude Code not detected)` | gate failed |
| `skipped (settings.json corrupt)` | JSON parse error |
| `skipped (write failed: <reason>)` | I/O error during write |

## Wizard flow change

Current order in `wizard.py`:

```
1. embedding (collect + probe)
2. vector / relation
3. server port
4. carry over ttl/search/recall
5. diff
6. unchanged → return early
7. write + ensure_dirs
8. server start/restart
```

New order (one step appended):

```
1. embedding (collect + probe)
2. vector / relation
3. server port
4. carry over ttl/search/recall
5. diff
6. unchanged → return early
7. write + ensure_dirs
8. server start/restart
9. claude hook install                       ← new
```

The hook install runs **after** server start (as the user requested). The install itself does not require the server to be up — but ordering it last reflects the user mental model "engine running → consumer wired up", and leaves room for future hook events that might want to health-check the running server.

## Implementation sketch

### `memorytalk/cli/recall.py`

Add a `--hook` flag. When set, the function:

```python
@click.command("recall")
@click.argument("session_id", required=False, default=None)
@click.argument("prompt", required=False, default=None)
@click.option("--hook", "hook_mode", is_flag=True, default=False,
              help="Read Claude Code UserPromptSubmit payload from stdin; "
                   "emit Claude hookSpecificOutput JSON. Errors are silent.")
@click.option("--top-k", ...)  # unchanged
@click.option("--data-root", ...)  # unchanged
@click.option("--json", "json_out", ...)  # unchanged
def recall(session_id, prompt, hook_mode, top_k, data_root, json_out):
    if hook_mode:
        _run_hook_mode(top_k, data_root)
        return
    # existing CLI mode unchanged
    ...


def _run_hook_mode(top_k, data_root) -> None:
    """UserPromptSubmit hook entry. Always exits 0; emits hook JSON to stdout."""
    def _emit(ctx: str) -> None:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": ctx,
            }
        }, sys.stdout)
        sys.stdout.write("\n")

    try:
        payload = json.loads(sys.stdin.read())
        session_id = payload["session_id"]
        prompt = payload["prompt"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"memory-talk hook: malformed stdin ({e})", file=sys.stderr)
        _emit("")
        return

    cfg = Config(data_root) if data_root else Config()
    body = {"session_id": session_id, "query": prompt}
    if top_k is not None:
        body["top_k"] = top_k

    try:
        result = api("POST", "/v2/recall", cfg, json_body=body, timeout=2.0)
    except Exception as e:
        print(f"memory-talk hook: recall failed ({e})", file=sys.stderr)
        _emit("")
        return

    recalled = result.get("recalled") or []
    if not recalled:
        _emit("")
        return

    lines = ["Recalled from prior sessions:", ""]
    for hit in recalled:
        lines.append(f"- [{hit['card_id']}] {hit['summary']}")
    _emit("\n".join(lines))
```

Key invariants:
- Always exits 0 in `--hook` mode (no `sys.exit(1)`, no uncaught exceptions reaching the shell).
- All errors funnel through `_emit("")`.
- Diagnostic strings on stderr only; stdout is strictly the hook JSON.

### `memorytalk/cli/setup/steps/claude_hook.py` (new)

```python
import json
import shutil
from pathlib import Path

from memorytalk.util.console import err_console, section
from memorytalk.util.settings_io import write_settings_atomic

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS = CLAUDE_DIR / "settings.json"
COMMAND = "memory-talk recall --hook"
SOURCE_TAG = "memory-talk"

ENTRY_TEMPLATE = {
    "type": "command",
    "command": COMMAND,
    "async": False,
    "_source": SOURCE_TAG,
}


def _step_claude_hook() -> dict:
    """Install / refresh the UserPromptSubmit hook in ~/.claude/settings.json.

    Returns {"status": "installed" | "updated" | "unchanged" | "skipped",
             "reason": "..." (only when skipped)}
    """
    section("Claude Code hook")

    # Gate
    if not CLAUDE_DIR.is_dir():
        err_console.print("[dim]~/.claude not found — skipping hook install[/dim]")
        return {"status": "skipped", "reason": "Claude Code not detected"}
    if shutil.which("claude") is None:
        err_console.print("[dim]`claude` not on $PATH — skipping hook install[/dim]")
        return {"status": "skipped", "reason": "Claude Code not detected"}

    # Read existing settings
    if SETTINGS.exists():
        try:
            data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            err_console.print(
                f"[yellow]warning:[/yellow] {SETTINGS} is corrupt JSON — "
                f"skipping ({e})"
            )
            return {"status": "skipped", "reason": "settings.json corrupt"}
    else:
        data = {}

    # Find or create the path
    hooks_root = data.setdefault("hooks", {})
    ups_blocks = hooks_root.setdefault("UserPromptSubmit", [])

    # Search for existing entry tagged _source=memory-talk
    existing_entry = None
    for block in ups_blocks:
        for entry in block.get("hooks", []):
            if isinstance(entry, dict) and entry.get("_source") == SOURCE_TAG:
                existing_entry = entry
                break
        if existing_entry is not None:
            break

    if existing_entry is None:
        # Append new block
        ups_blocks.append({"hooks": [dict(ENTRY_TEMPLATE)]})
        action = "installed"
    else:
        # Compare canonical fields (preserve any user-added unknown fields)
        diffed = any(
            existing_entry.get(k) != v for k, v in ENTRY_TEMPLATE.items()
        )
        if not diffed:
            err_console.print("[green]✓[/green] Claude hook already correct")
            return {"status": "unchanged"}
        for k, v in ENTRY_TEMPLATE.items():
            existing_entry[k] = v
        action = "updated"

    # Atomic write
    try:
        write_settings_atomic(SETTINGS, data)
    except OSError as e:
        err_console.print(f"[yellow]warning:[/yellow] write to {SETTINGS} failed ({e})")
        return {"status": "skipped", "reason": f"write failed: {e}"}

    err_console.print(f"[green]✓[/green] Claude hook {action} → {SETTINGS}")
    return {"status": action}
```

### `memorytalk/cli/setup/wizard.py`

Add the call at the end of the success path (after server step, before the return):

```python
from .steps.claude_hook import _step_claude_hook
...
server_payload = _step_server(cfg, old_raw is not None and bool(changed))
hook_payload = _step_claude_hook()

return {
    "settings_changed": changed,
    "wrote_settings": True,
    "ensured_dirs": True,
    "server": server_payload,
    "claude_hook": hook_payload,
    "first_install": is_first_install,
}
```

The early-return path (when `not changed`) does not run `_step_claude_hook` — same gate as `_step_server`. Re-running setup with no changes won't reinstall the hook. Hook install is part of "wiring up the install", which doesn't apply to a no-op rerun. (If we later decide every setup run should re-validate the hook the same way the embedding probe does, that's a one-line change to move the call above the early-return.)

### `memorytalk/cli/setup/__init__.py`

After `result = _wizard(...)`, the result dict carries `claude_hook` already; no further wiring needed beyond passing it to `_summary_md`.

### `memorytalk/cli/setup/summary.py`

Add a `_hook_label(payload: dict | None)` and a row insertion between PATH takeover and changed:

```python
takeover = result.get("path_takeover") or {}
rows.append(("PATH takeover", _takeover_label(takeover)))

hook = result.get("claude_hook") or {"status": "unchanged"}
rows.append(("claude hook", _hook_label(hook)))

rows.append(("changed", _changed_label(result)))
```

```python
def _hook_label(payload: dict) -> str:
    status = payload.get("status", "unchanged")
    if status in ("installed", "updated", "unchanged"):
        return status
    if status == "skipped":
        reason = payload.get("reason", "")
        return f"skipped ({reason})" if reason else "skipped"
    return status
```

## Testing

### `tests/cli/recall/test_hook_mode/` (new)

Direct unit-ish tests of `--hook` mode invocation:

- **success path**: stdin contains valid JSON → `httpx` mock returns 200 with two RecallHits → assert stdout JSON has `hookSpecificOutput.additionalContext` containing both `card_id`s as bullets.
- **empty recall**: server returns `recalled: []` → assert `additionalContext == ""`.
- **server down**: `httpx` raises ConnectError → assert `additionalContext == ""`, exit 0, stderr contains diagnostic.
- **malformed stdin**: feed non-JSON garbage → assert `additionalContext == ""`, exit 0.
- **missing fields**: stdin JSON without `prompt` → assert `additionalContext == ""`, exit 0.
- **server returns 5xx**: assert `additionalContext == ""`, exit 0.

### `tests/cli/setup/test_claude_hook_install/` (new)

Integration-style with the existing setup fixture, plus monkeypatch on `Path.home()` (already done in conftest) and on `shutil.which` for `claude` detection:

- **gate fails (no ~/.claude)**: ensure step returns `skipped`, summary row says so, no file writes.
- **gate fails (no claude binary)**: monkeypatch `shutil.which("claude")` → None, assert `skipped`.
- **fresh install**: gate passes, `~/.claude/settings.json` doesn't exist → settings.json created with one UserPromptSubmit entry tagged `_source: memory-talk`.
- **existing settings, no memory-talk entry**: settings.json has unrelated hooks → step appends our entry, leaves others untouched.
- **existing memory-talk entry, command unchanged**: returns `unchanged`, file mtime not bumped.
- **existing memory-talk entry, command differs**: returns `updated`, command field refreshed, sibling unknown fields preserved.
- **corrupt settings.json**: returns `skipped` with `reason="settings.json corrupt"`, file not modified.

## Pre-implementation step (manual verification)

Before writing the recall `--hook` mode tests, the implementer must verify the actual stdin payload Claude Code sends for UserPromptSubmit. The spec assumes the field names are `session_id` and `prompt`. To confirm:

1. Manually create a temporary hook in `~/.claude/settings.json`:

   ```json
   {
     "hooks": {
       "UserPromptSubmit": [
         {"hooks": [{"type": "command",
                     "command": "cat > /tmp/claude-hook-debug.log",
                     "async": false}]}
       ]
     }
   }
   ```

2. Open a Claude Code session, send any user prompt.
3. Inspect `/tmp/claude-hook-debug.log` to confirm the JSON shape and field names.
4. Remove the temporary entry.

If the field names differ from the spec's assumption, update the parsing logic and tests before proceeding. This step is mandatory — getting the field name wrong would invalidate every mock in the test suite.

## Out of scope

- Cursor support (the `hooks-cursor.json` plugin variant) — same shape, but separate iteration. We'll add it once the Claude path is proven.
- Other Claude Code hook events (PreToolUse / PostToolUse / Stop / etc.) — UserPromptSubmit only.
- Claude session ID ↔ memory-talk session ID mapping. Direct passthrough now; mapping is a future feature.
- Hook removal / uninstall CLI. If a user wants to remove the entry, they edit `~/.claude/settings.json` manually; we'll add a CLI later if needed.
- Conflict detection with the plugin-marketplace install. The plugin variant uses SessionStart with `${CLAUDE_PLUGIN_ROOT}` references; we install UserPromptSubmit. They don't overlap. If a user has both, both fire — different events, different injection. No interference.
- Hook latency optimization. The current shape pays Python startup + memorytalk import on every prompt (~300-500ms). Acceptable for v0; revisit if user reports it's painful.
