"""Shared ingest helper for fixture-style tests.

The HTTP API exposes ``ensure`` + ``append`` (cursor-based, append-only).
Many tests don't care about the cursor — they just want to set up a
session in the DB and move on. This helper hides the ensure → filter →
append dance behind a one-call interface that mimics the old whole-
session ``POST /v3/sessions`` shape: pass in the rounds, the helper
figures out which ones are new relative to the server's current cursor
and submits those.

Pure HTTP — works against any ``client`` fixture in this suite.
"""
from __future__ import annotations
from typing import Any

import httpx


async def ingest_session(
    client: httpx.AsyncClient,
    session_id: str,
    *,
    source: str = "claude-code",
    location: str = "",
    rounds: list[dict],
    created_at: str = "2026-05-20T00:00:00Z",
    metadata: dict[str, Any] | None = None,
) -> httpx.Response:
    """Ensure-then-append. Returns the ``/sessions/append`` response.

    Mints the canonical session_id from the raw upstream id via the
    appropriate adapter (mirrors what SyncWatcher does in production).
    Tests pass a raw upstream id (like ``"src-1"``) and get back a
    minted ``sess-<loc8>-<lastseg>`` id in the response payload.
    """
    metadata = metadata if metadata is not None else {"cwd": "/work/proj"}

    # Mint canonical id via the source's adapter (default location).
    from memorytalk.adapters import ADAPTERS
    cls = ADAPTERS.get(source)
    if cls is None:
        raise ValueError(f"unknown source {source!r} in test helper")
    loc = location or cls.DEFAULT_LOCATION or ""
    adapter = cls(location=loc)
    sid = adapter.mint_session_id(session_id)

    r = await client.post("/v3/sessions/ensure", json={
        "session_id": sid, "source": source, "location": loc,
    })
    r.raise_for_status()
    server_last = r.json().get("last_round_id")

    if server_last is None:
        new_rounds = list(rounds)
    else:
        new_rounds = []
        seen = False
        for round_ in rounds:
            if not seen:
                if round_.get("round_id") == server_last:
                    seen = True
                continue
            new_rounds.append(round_)
        if not seen:
            # Divergent payload (marker missing). The append below will
            # be empty and idempotent.
            new_rounds = []

    return await client.post("/v3/sessions/append", json={
        "session_id": sid, "source": source, "location": loc,
        "expected_prev_round_id": server_last,
        "rounds": new_rounds,
        "created_at": created_at,
        "metadata": metadata,
    })
