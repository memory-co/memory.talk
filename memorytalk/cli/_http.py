"""HTTP client helpers for CLI commands.

Tests can override `_make_client` to route requests through an in-process
ASGI transport instead of a real TCP socket — this lets test cases exercise
the full CLI code path without spawning uvicorn.
"""
from __future__ import annotations
from typing import Any, Callable, Optional

import httpx

from memorytalk.config import Config


class ApiError(RuntimeError):
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"API {status_code}: {payload}")


def extract_error_message(payload: Any) -> str:
    """Pull a single human-readable message string out of whatever shape the
    server (or the CLI) handed us as an error payload.

    FastAPI tends to return ``{"detail": "..."}``. Our own services return
    ``{"error": "..."}``. The rebuild gate returns ``{"error": "rebuilding"}``.
    Some paths produce nested dicts. Plain strings come through too.
    """
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("error", "detail", "message"):
            v = payload.get(key)
            if isinstance(v, str) and v:
                return v
            if isinstance(v, dict):
                # one level of unwrap, e.g. {"error": {"detail": "..."}}
                return extract_error_message(v)
        # Fall back to a compact JSON-ish dump
        try:
            import json as _json
            return _json.dumps(payload, ensure_ascii=False)
        except Exception:
            return str(payload)
    return str(payload)


def resolve_port(cfg: Config) -> int:
    """Return the port the daemon is (or should be) listening on.

    Discovery order:
      1. ``server.port`` file written by ``server start`` — preferred,
         independent of settings.json. This means a settings.json that
         fails to render (missing ``${VAR}``, legacy ``auth_env_key``,
         etc.) does not break CLI commands that only need to talk to a
         live server — the env var matters at server-startup time, not
         at every CLI invocation.
      2. ``cfg.settings.server.port`` — fallback for installs that
         predate the port file or where it got removed while the daemon
         is still running. May raise ``ConfigValidationError``; callers
         that want graceful degradation should catch it.
    """
    if cfg.port_path.exists():
        try:
            return int(cfg.port_path.read_text().strip())
        except ValueError:
            pass  # fall through to settings
    return cfg.settings.server.port


def _default_client(cfg: Config) -> httpx.Client:
    base = f"http://127.0.0.1:{resolve_port(cfg)}"
    return httpx.Client(base_url=base, timeout=30.0)


# Test hook: set to a callable(Config) -> httpx.Client to override transport
# (e.g. route to an in-process ASGI app instead of 127.0.0.1:<port>).
_make_client: Optional[Callable[[Config], httpx.Client]] = None


def api(method: str, path: str, config: Config,
        json_body: dict | None = None, timeout: float = 30.0,
        params: dict | list[tuple[str, str]] | None = None) -> dict:
    factory = _make_client or _default_client
    client = factory(config)
    # No `with` — ASGI test transport has no context-manager support, and
    # the CLI is a short-lived process where leaked TCP sockets get reaped
    # at exit. Tests share a long-lived ASGI client across calls.
    resp = client.request(method, path, json=json_body, timeout=timeout, params=params)
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        raise ApiError(resp.status_code, payload)
    return resp.json()
