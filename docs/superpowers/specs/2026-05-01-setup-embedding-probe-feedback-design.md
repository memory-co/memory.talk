# Setup: embedding probe feedback

**Date:** 2026-05-01
**Scope:** `memory-talk setup` wizard — embedding step only.
**Status:** Approved (brainstorming session 2026-05-01).

## Why

Today the embedding probe is invisible to the user:

- On success, `_step_probe_embedding` returns silently — the wizard advances and the user has no positive signal that the API was actually exercised.
- The probe only fires when the embedding section diffs against `old_raw`, or on first install. A user re-running `memory-talk setup` to "check things still work" gets no probe at all when nothing was edited.

The longer-term shape we're heading toward is "every wizard step ends with a one-line ack". This spec lands the first instance — embedding only — and establishes the pattern. Other steps will follow in their own specs.

## What changes

### Behavior

1. **Probe runs on every setup invocation**, not only when `embedding_changed` or `is_first_install`. Setup becomes a usable health check: `memory-talk setup` → enter through every prompt → probe re-validates the live config.
2. **A spinner is shown while the probe is in flight.** Local-model loading can take 10+ seconds; HTTP probes take a few hundred ms — both warrant "the tool is doing something" feedback.
3. **On success, a single confirmation line is printed** with the model, configured dim, and observed latency:

   ```
   ✓ embedding verified · text-embedding-v4 · dim 1024 · 412ms
   ```

   Latency formatted as `{int}ms` below 1000 ms, `{x.x}s` at or above.

4. **Failure path is unchanged.** `EmbedderValidationError` still triggers the existing re-edit loop; no ✓ line and no latency on failure (the error message carries the diagnostic value).

### Wizard flow change

Current order in `wizard.py`:

```
1. collect inputs (embedding, vector, relation, server port)
2. compute `changed` (diff vs old_raw)
3. if old_raw and not changed → print "nothing to write", return
4. if embedding_changed or first_install → probe
5. write + ensure_dirs
6. server step
```

New order:

```
1. collect inputs
2. compute `changed`
3. probe (always)                         ← moved up, gated removed
4. if old_raw and not changed → print "nothing to write", return
5. write + ensure_dirs
6. server step
```

The "embedding_changed" gate is deleted. The "config unchanged → return early" branch stays exactly as it is, just moved one step later so probe always runs first.

Edge case: probe failure during a re-edit loop mutates `new_settings`. If the user originally had no diff but ended up editing fields to fix a broken config, the diff is now non-empty and the wizard naturally proceeds to write the corrected settings. No special handling required.

## Implementation sketch

### `memorytalk/cli/setup/steps/embedding.py`

```python
import time

def _fmt_latency(seconds: float) -> str:
    ms = seconds * 1000
    if ms < 1000:
        return f"{int(ms)}ms"
    return f"{seconds:.1f}s"


def _step_probe_embedding(cfg: Config, new_settings: dict) -> None:
    cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
    while True:
        try:
            t0 = time.perf_counter()
            with err_console.status("[dim]validating embedding endpoint…[/dim]"):
                asyncio.run(validate_embedder(cfg))
            elapsed = time.perf_counter() - t0
            emb = new_settings["embedding"]
            err_console.print(
                f"[green]✓[/green] embedding verified · "
                f"{emb['model']} · dim {emb['dim']} · {_fmt_latency(elapsed)}"
            )
            return
        except EmbedderValidationError as e:
            err_console.print(f"[red]embedding probe failed:[/red] {e}")
            if not _prompt.confirm("Re-edit embedding fields?", default=True):
                sys.exit(1)
            new_settings.update(_step_embedding(new_settings))
            cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
```

Notes:

- `err_console.status(...)` is rich's spinner context manager — already a project dependency. The spinner is automatically cleared on context exit; the ✓ line lands cleanly underneath.
- Timing wraps the entire `asyncio.run(validate_embedder(cfg))` call. The user sees wall-clock latency (which is what they care about), including any framework overhead.
- The success line reads `model` and `dim` from `new_settings["embedding"]`, not from a return value of `validate_embedder`. The probe's contract — "raise on failure, return None on success" — is preserved. This keeps the probe reusable as a startup-time health check elsewhere without UI coupling.

### `memorytalk/cli/setup/wizard.py`

Replace the conditional probe + early-return block:

```python
# was:
if old_raw is not None and not changed:
    err_console.print("\n[dim]config unchanged — nothing to write[/dim]")
    return {...}

embedding_changed = old_raw is None or new_settings.get("embedding") != (old_raw.get("embedding") or {})
if embedding_changed:
    _step_probe_embedding(cfg, new_settings)
```

with:

```python
_step_probe_embedding(cfg, new_settings)

if old_raw is not None and not changed:
    err_console.print("\n[dim]config unchanged — nothing to write[/dim]")
    return {...}
```

`embedding_changed` and the gate are deleted.

## Testing

### Existing tests (5 setup integration tests)

- `test_first_install_openai`, `test_first_install_local`, `test_reconfigure_changed`, `test_optout_uses_current_env` — already mock `validate_embedder` / `mock_openai_probe`. Pass through the new flow unchanged.
- `test_reconfigure_no_change` — already pre-mocks the probe defensively (per its README). Under the new flow that mock is now actually exercised. Its existing assertion `"nothing" + "unchanged" in stdout` still holds, because the early-return branch still prints the same line; it just runs after the probe instead of before.
- `test_path_takeover`, `test_bootstrap_real_venv` — do not touch the embedding flow.

### New assertion

In `test_first_install_openai` (or a sibling test), assert the success line is printed:

- stdout contains `embedding verified`
- stdout contains the model name (`text-embedding-v4`)
- stdout contains `dim 1024`
- stdout contains either `ms` or `s` (latency unit; the numeric value is unstable and not asserted)

No new test scaffolding is required — the existing fixtures already capture stderr/stdout.

## Out of scope

- Validation feedback for other wizard steps (vector, relation, server port, PATH takeover). Each gets its own spec when we extend the pattern. The shape (`✓ <step> verified · <key params>`) is intentionally consistent so future steps can be lifted into a small helper if duplication appears.
- Changes to `validate_embedder`'s return type or to the probe's contract.
- Any caching of "we just probed, skip next time" — the user explicitly wants every run to re-validate.
