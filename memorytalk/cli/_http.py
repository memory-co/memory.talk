"""HTTP client helpers for CLI commands.

Tests override ``_make_client`` to route requests through an in-process
ASGI transport — no real TCP socket, no real port. This lets tests
exercise the full CLI code path without spawning uvicorn.
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
    """Pull a human-readable message out of whatever shape the server / CLI
    handed us as an error payload."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("error", "detail", "message"):
            v = payload.get(key)
            if isinstance(v, str) and v:
                return v
            if isinstance(v, dict):
                return extract_error_message(v)
        try:
            import json as _json
            return _json.dumps(payload, ensure_ascii=False)
        except Exception:
            return str(payload)
    return str(payload)


def resolve_port(cfg: Config) -> int:
    """Discover the port the daemon is listening on.

    1. ``server.port`` file written by ``server start`` — preferred,
       independent of settings.json (a broken ${VAR} render won't make a
       live server look dead to CLI commands that only talk to it).
    2. ``cfg.settings.server.port`` — fallback.
    """
    if cfg.port_path.exists():
        try:
            return int(cfg.port_path.read_text().strip())
        except ValueError:
            pass
    return cfg.settings.server.port


def _default_client(cfg: Config) -> httpx.Client:
    base = f"http://127.0.0.1:{resolve_port(cfg)}"
    # trust_env=False: never route the loopback call to the local daemon
    # through HTTP(S)_PROXY / NO_PROXY env — a configured proxy would
    # otherwise intercept 127.0.0.1 and surface as "Server disconnected".
    return httpx.Client(base_url=base, timeout=30.0, trust_env=False)


_make_client: Optional[Callable[[Config], httpx.Client]] = None


def api(method: str, path: str, config: Config,
        json_body: dict | None = None, timeout: float = 30.0,
        params: dict | list[tuple[str, str]] | None = None) -> Any:
    """Call the server. Raises ApiError on 4xx/5xx. Returns the JSON body."""
    factory = _make_client or _default_client
    client = factory(config)
    # No `with` — the ASGI test transport has no context-manager support, and
    # the CLI is short-lived; leaked TCP sockets get reaped at process exit.
    resp = client.request(method, path, json=json_body, timeout=timeout, params=params)
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        raise ApiError(resp.status_code, payload)
    return resp.json()
