"""Search-quality test infrastructure.

- `baselines` (session-scoped): dict loaded from `_baselines.json`. Tests
  read it for regression checks and the runner writes to it (in-memory)
  when they hit the Excellent band.
- `pytest_sessionfinish`: when `UPDATE_BASELINES=1` is set, persists the
  in-memory baselines back to `_baselines.json`. Default (env var absent)
  never writes — CI runs are read-only.

Per-mode app_clients live in `pure_fts/conftest.py` and
`fts_plus_vector/conftest.py`.
"""
from __future__ import annotations
import os
from pathlib import Path

import pytest

from memorytalk.tests.search._quality import load_baselines, save_baselines


_BASELINES_PATH = Path(__file__).parent / "_baselines.json"

# Module-level dict so pytest_sessionfinish can persist it after the
# session-scoped fixture has gone out of scope.
_LIVE_BASELINES: dict[str, float] = {}


@pytest.fixture(scope="session")
def baselines():
    """Live baseline dict — loaded once per session, mutated by run_case."""
    _LIVE_BASELINES.clear()
    _LIVE_BASELINES.update(load_baselines(_BASELINES_PATH))
    return _LIVE_BASELINES


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("UPDATE_BASELINES") != "1":
        return
    if not _LIVE_BASELINES:
        return
    save_baselines(_BASELINES_PATH, _LIVE_BASELINES)
