"""Wizard step: pick embedding provider + probe it.

`_step_embedding` walks the user through provider/model/dim/auth and
returns a fresh ``new_settings`` dict with the ``embedding`` block
filled in. `_step_probe_embedding` then exercises the provider with a
real (mocked in tests) request — if it fails the user gets a chance to
edit fields and retry.
"""
from __future__ import annotations
import asyncio
import sys

from rich.prompt import Confirm, IntPrompt, Prompt

from memorytalk.config import Config, Settings
from memorytalk.provider.embedding import (
    EmbedderValidationError, validate_embedder,
)

from .._io import err_console


def _step_embedding(base: dict) -> dict:
    out = {k: v for k, v in base.items()}
    cur_emb = base.get("embedding") or {}
    cur_provider = cur_emb.get("provider")
    default_provider = cur_provider if cur_provider in ("local", "openai") else "openai"

    provider = Prompt.ask(
        "embedding provider",
        choices=["local", "openai"], default=default_provider,
        console=err_console,
    )

    # Provider-specific defaults shouldn't bleed across providers.
    if cur_provider != provider:
        cur_emb = {}

    if provider == "openai":
        endpoint = Prompt.ask(
            "endpoint",
            default=cur_emb.get("endpoint") or "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            console=err_console,
        )
        auth_env_key = Prompt.ask(
            "auth env var name",
            default=cur_emb.get("auth_env_key") or "QWEN_KEY",
            console=err_console,
        )
        model = Prompt.ask(
            "model", default=cur_emb.get("model") or "text-embedding-v4",
            console=err_console,
        )
        dim = IntPrompt.ask(
            "dim", default=int(cur_emb.get("dim") or 1024),
            console=err_console,
        )
        out["embedding"] = {
            "provider": "openai", "endpoint": endpoint,
            "auth_env_key": auth_env_key, "model": model, "dim": dim,
            "timeout": cur_emb.get("timeout", 30.0),
        }
    else:
        model = Prompt.ask(
            "model", default=cur_emb.get("model") or "all-MiniLM-L6-v2",
            console=err_console,
        )
        dim = IntPrompt.ask(
            "dim", default=int(cur_emb.get("dim") or 384),
            console=err_console,
        )
        out["embedding"] = {
            "provider": "local", "model": model, "dim": dim,
            "endpoint": None, "auth_env_key": None,
            "timeout": cur_emb.get("timeout", 30.0),
        }
    return out


def _step_probe_embedding(cfg: Config, new_settings: dict) -> None:
    cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
    while True:
        try:
            asyncio.run(validate_embedder(cfg))
            return
        except EmbedderValidationError as e:
            err_console.print(f"[red]embedding probe failed:[/red] {e}")
            if not Confirm.ask("Re-edit embedding fields?", console=err_console, default=True):
                sys.exit(1)
            new_settings.update(_step_embedding(new_settings))
            cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
