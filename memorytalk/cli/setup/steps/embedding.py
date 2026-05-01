"""Wizard step: pick embedding provider + probe it.

Uses the ``console`` shim throughout. Provider/endpoint/auth/model are
arrow-key selects with a final "Other..." entry that drops to free text
— so the common cases are one keypress and the long tail still works.
``dim`` is auto-derived from the chosen model when picked from the known
list; only "Other..." asks for it.

When a previous run already set a custom value (e.g. an endpoint URL
that's not in our known list), ``_select_or_text`` surfaces it as the
top option marked ``(current)`` and pre-selects it, so reconfigure is
one keypress to keep the existing value.

Endpoint URLs and auth-env-var names are shown raw (no friendly
aliases) — the value IS the answer; wrapping it in a brand label only
hides what the user is picking.

The probe loop is kept identical: validate, on failure ask whether to
re-edit the embedding section, retry until success or user gives up.
"""
from __future__ import annotations
import asyncio
import sys
import time

from memorytalk.config import Config, Settings
from memorytalk.provider.embedding import (
    EmbedderValidationError, validate_embedder,
)

from memorytalk.util import console
from memorytalk.util.console import err_console, section


def _fmt_latency(seconds: float) -> str:
    """Format latency in seconds to a human-readable string.

    < 1000ms renders as "{int}ms"; >= 1.0s renders as "{x.x}s" (1 decimal).
    """
    ms = seconds * 1000
    if ms < 1000:
        return f"{int(ms)}ms"
    return f"{seconds:.1f}s"


# Known model → canonical embedding dim. Keeps users from having to know
# the exact dim for the model they picked (it's a footgun otherwise).
KNOWN_OPENAI_MODELS: dict[str, int] = {
    "text-embedding-v4": 1024,         # Dashscope/Qwen
    "text-embedding-v3": 1024,         # Dashscope/Qwen
    "text-embedding-3-large": 3072,    # OpenAI
    "text-embedding-3-small": 1536,    # OpenAI
    "text-embedding-ada-002": 1536,    # OpenAI legacy
}

KNOWN_LOCAL_MODELS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "BAAI/bge-large-en-v1.5": 1024,
}

# Raw URLs — no alias / brand title. The URL is what the user is choosing.
KNOWN_ENDPOINTS = [
    console.Option("https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"),
    console.Option("https://api.openai.com/v1/embeddings"),
]

_OTHER = "__other__"


def _select_or_text(
    label: str,
    known: list[console.Option],
    *,
    current: str | None = None,
) -> str:
    """Pick from ``known`` + Other..., with the user's existing value
    surfaced as the top option if it's not already in the known list.

    ``current`` is the value already set in settings (None on first
    install). Behavior:

    - If ``current`` matches a known option → pre-select that.
    - If ``current`` is custom → prepend an option with value=current,
      marked ``(current)``, and pre-select it.
    - If no ``current`` → fall back to the first known as default.
    - "Other..." always offered → drops to free text.
    """
    options: list[console.Option] = []
    if current and not any(o.value == current for o in known):
        options.append(console.Option(current, description="(current)"))
    options.extend(known)
    options.append(console.Option(_OTHER, title="Other... (type your own)"))

    sel_default = current if current else (known[0].value if known else _OTHER)

    sel = console.select(label, options, default=sel_default)
    if sel == _OTHER:
        return console.text(f"{label} (custom)", default=current or "")
    return sel


def _select_model_and_dim(
    known: dict[str, int],
    default_model: str,
    default_dim: int,
) -> tuple[str, int]:
    options = [console.Option(m, description=f"dim {d}") for m, d in known.items()]
    options.append(console.Option(_OTHER, title="Other... (type your own)"))
    sel_default = default_model if default_model in known else _OTHER
    sel = console.select("embedding model", options, default=sel_default)
    if sel != _OTHER:
        return sel, known[sel]
    model = console.text("embedding model (custom)", default=default_model)
    dim_str = console.text(
        "embedding dim", default=str(default_dim),
        validate=lambda v: (v.strip().isdigit() and int(v) > 0) or "must be a positive integer",
    )
    return model, int(dim_str)


def _step_embedding(base: dict) -> dict:
    section("Embedding")

    out = dict(base)
    cur_emb = base.get("embedding") or {}
    cur_provider = cur_emb.get("provider")
    default_provider = cur_provider if cur_provider in ("local", "openai") else "openai"

    provider = console.select(
        "embedding provider",
        [
            console.Option("openai", description="OpenAI-compatible HTTP API"),
            console.Option("local", description="sentence-transformers (local CPU/GPU)"),
        ],
        default=default_provider,
    )

    # Provider-specific defaults shouldn't bleed across providers.
    if cur_provider != provider:
        cur_emb = {}

    if provider == "openai":
        endpoint = _select_or_text(
            "embedding endpoint",
            KNOWN_ENDPOINTS,
            current=cur_emb.get("endpoint"),
        )
        # auth_key holds the literal API key. ${VAR} interpolation still
        # exists for tests but is not advertised — the cross-context env
        # mismatch (setup shell vs server-runtime context) is a footgun
        # we don't want users routinely reaching for.
        auth_key = console.text(
            "auth key",
            default=cur_emb.get("auth_key") or "",
        )
        model, dim = _select_model_and_dim(
            KNOWN_OPENAI_MODELS,
            cur_emb.get("model") or "text-embedding-v4",
            int(cur_emb.get("dim") or 1024),
        )
        out["embedding"] = {
            "provider": "openai", "endpoint": endpoint,
            "auth_key": auth_key, "model": model, "dim": dim,
            "timeout": cur_emb.get("timeout", 30.0),
        }
    else:
        model, dim = _select_model_and_dim(
            KNOWN_LOCAL_MODELS,
            cur_emb.get("model") or "all-MiniLM-L6-v2",
            int(cur_emb.get("dim") or 384),
        )
        out["embedding"] = {
            "provider": "local", "model": model, "dim": dim,
            "endpoint": None, "auth_key": None,
            "timeout": cur_emb.get("timeout", 30.0),
        }
    return out


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
            if not console.confirm("Re-edit embedding fields?", default=True):
                sys.exit(1)
            new_settings.update(_step_embedding(new_settings))
            cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
