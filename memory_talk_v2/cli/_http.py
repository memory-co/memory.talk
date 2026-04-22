"""HTTP client helpers for CLI commands."""
from __future__ import annotations
from typing import Any

import httpx

from memory_talk_v2.config import Config


class ApiError(RuntimeError):
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"API {status_code}: {payload}")


def api(method: str, path: str, config: Config, json_body: dict | None = None, timeout: float = 30.0) -> dict:
    url = f"http://127.0.0.1:{config.settings.server.port}{path}"
    resp = httpx.request(method, url, json=json_body, timeout=timeout)
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        raise ApiError(resp.status_code, payload)
    return resp.json()
