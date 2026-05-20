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
    rounds: list[dict],
    created_at: str = "2026-05-20T00:00:00Z",
    metadata: dict[str, Any] | None = None,
) -> httpx.Response:
    """Ensure-then-append. Returns the ``/sessions/append`` response.

    ``rounds`` is the **whole** session as the caller sees it; this
    helper filters out everything up to and including the server's
    current ``last_round_id`` before posting, matching the natural
    test-fixture intent ("here's the session, make sure it's stored").
    """
    metadata = metadata if metadata is not None else {"cwd": "/work/proj"}

    r = await client.post("/v3/sessions/ensure", json={
        "session_id": session_id, "source": source,
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
        "session_id": session_id, "source": source,
        "expected_prev_round_id": server_last,
        "rounds": new_rounds,
        "created_at": created_at,
        "metadata": metadata,
    })
