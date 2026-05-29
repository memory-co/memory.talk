"""LanceStore EMFILE recovery + single retry.

The search wrapper around ``_run_hybrid`` must catch Lance's wrapped
"Too many open files" error, drive a compaction + connection reset,
and retry exactly once. These tests fake the EMFILE so we can drive
the recovery branch deterministically — actually exhausting the fd
table mid-test would be flaky + slow.
"""
from __future__ import annotations
import pytest

from memorytalk.provider.lancedb import _is_emfile


# Note: ``asyncio_mode=auto`` (set in pyproject) auto-marks async
# functions, so a module-level ``pytestmark = pytest.mark.asyncio``
# would spuriously apply to the sync ``_is_emfile`` tests below.


# ────────── _is_emfile string match ──────────

def test_is_emfile_matches_lance_string():
    """Lance wraps the OS error inside LanceError(IO) before raising —
    we match by string. Pin the exact substrings we look for."""
    e = RuntimeError(
        "lance error: LanceError(IO): Too many open files (os error 24)"
    )
    assert _is_emfile(e)


def test_is_emfile_matches_os_error_24_alone():
    """Some Lance versions emit the errno without the human text."""
    e = RuntimeError("LanceError(IO): some message (os error 24)")
    assert _is_emfile(e)


def test_is_emfile_rejects_unrelated_errors():
    assert not _is_emfile(RuntimeError("some other error"))
    assert not _is_emfile(ValueError("bad input"))


# ────────── recovery path ──────────

async def test_search_retries_after_emfile_recovery(app, monkeypatch):
    """First call raises EMFILE → recovery runs → second call succeeds."""
    vectors = app.state.vectors

    # Pre-populate the rounds table so _exists passes + search has data.
    await vectors.add_rounds([{
        "session_id": "sess-x", "idx": 1, "role": "human",
        "text": "hello", "vector": [0.0] * 384,
    }])

    from memorytalk.provider import lancedb as lance_mod

    calls = {"count": 0}
    original_run = lance_mod._run_hybrid

    async def flaky(table, *a, **kw):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError(
                "lance error: LanceError(IO): Too many open files (os error 24)"
            )
        return await original_run(table, *a, **kw)

    monkeypatch.setattr(lance_mod, "_run_hybrid", flaky)
    before = vectors.emfile_recoveries

    # search_rounds → first _run_hybrid raises → recovery → retry → success.
    # Vector-only query so the retry path doesn't depend on an FTS
    # index existing on the rounds table.
    rows = await vectors.search_rounds("", [0.0] * 384, top_k=5)
    assert calls["count"] == 2  # one fail + one retry
    assert vectors.emfile_recoveries == before + 1
    assert vectors.last_emfile_at_iso is not None
    # Retry returned real results.
    assert isinstance(rows, list)


async def test_search_propagates_non_emfile_error(app, monkeypatch):
    """Unrelated errors must NOT trigger recovery + retry."""
    vectors = app.state.vectors
    # Need at least one row so _exists(rounds) is True; otherwise
    # _search_with_recovery short-circuits to [] without ever calling
    # _run_hybrid (and the mock never fires).
    await vectors.add_rounds([{
        "session_id": "sess-x", "idx": 1, "role": "human",
        "text": "hi", "vector": [0.0] * 384,
    }])

    from memorytalk.provider import lancedb as lance_mod
    calls = {"count": 0}

    async def boom(table, *a, **kw):
        calls["count"] += 1
        raise RuntimeError("totally unrelated")

    monkeypatch.setattr(lance_mod, "_run_hybrid", boom)
    before = vectors.emfile_recoveries

    with pytest.raises(RuntimeError, match="totally unrelated"):
        await vectors.search_rounds("", [0.0] * 384, top_k=5)
    assert calls["count"] == 1  # no retry
    assert vectors.emfile_recoveries == before  # no recovery either


async def test_search_does_not_retry_after_second_emfile(app, monkeypatch):
    """If post-recovery query still EMFILEs, propagate — operator
    action is needed (the in-process recovery can't fix the underlying
    fd-budget vs fragment-count mismatch)."""
    vectors = app.state.vectors
    await vectors.add_rounds([{
        "session_id": "sess-x", "idx": 1, "role": "human",
        "text": "hi", "vector": [0.0] * 384,
    }])
    from memorytalk.provider import lancedb as lance_mod
    calls = {"count": 0}

    async def always_emfile(table, *a, **kw):
        calls["count"] += 1
        raise RuntimeError(
            "lance error: LanceError(IO): Too many open files (os error 24)"
        )

    monkeypatch.setattr(lance_mod, "_run_hybrid", always_emfile)

    with pytest.raises(RuntimeError, match="Too many open files"):
        await vectors.search_rounds("", [0.0] * 384, top_k=5)
    assert calls["count"] == 2  # original + one retry, then give up


async def test_concurrent_recoveries_share_work(app, monkeypatch):
    """Two concurrent EMFILE searches must drive recovery exactly once,
    not twice (otherwise we'd compact / reconnect serially N times for
    no reason)."""
    vectors = app.state.vectors
    await vectors.add_rounds([{
        "session_id": "sess-x", "idx": 1, "role": "human",
        "text": "hi", "vector": [0.0] * 384,
    }])

    from memorytalk.provider import lancedb as lance_mod
    original_run = lance_mod._run_hybrid
    state = {"fail_count": 2}  # both first attempts EMFILE; retries succeed

    async def flaky(table, *a, **kw):
        if state["fail_count"] > 0:
            state["fail_count"] -= 1
            raise RuntimeError(
                "lance error: LanceError(IO): Too many open files (os error 24)"
            )
        return await original_run(table, *a, **kw)

    monkeypatch.setattr(lance_mod, "_run_hybrid", flaky)
    before = vectors.emfile_recoveries

    import asyncio
    await asyncio.gather(
        vectors.search_rounds("", [0.0] * 384, top_k=5),
        vectors.search_rounds("", [0.0] * 384, top_k=5),
    )

    # Both calls succeeded, but only one recovery actually ran.
    assert vectors.emfile_recoveries == before + 1
