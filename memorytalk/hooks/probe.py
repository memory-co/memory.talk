"""End-to-end probe: spawn the host CLI with a magic token, then check
that ``recall --hook`` (running inside the host's UserPromptSubmit) wrote
a sentinel file. Robust to host-CLI stdout formatting changes."""
from __future__ import annotations

import subprocess
import tempfile
import time
import uuid
from pathlib import Path


PROBE_PREFIX = "memorytalk-probe-"
PROBE_TIMEOUT_S = 25


def new_token() -> str:
    return f"{PROBE_PREFIX}{uuid.uuid4().hex}"


def sentinel_path(token: str) -> Path:
    return Path(tempfile.gettempdir()) / f"{token}.ok"


def run_probe(argv: list[str]) -> bool:
    """Spawn the host CLI with a probe argv. Returns True iff the sentinel
    file matching the embedded token appears within the timeout.

    The token must be derivable from ``argv`` (we scan argv for the prefix).
    If the host CLI returns non-zero (no API key, model error, etc.) but
    the hook still fired before the model call, the sentinel will exist
    and we still count it as success — the goal is to prove the hook
    pipeline, not the host's ability to talk to a model."""
    token = next((a for a in argv if a.startswith(PROBE_PREFIX)), None)
    if token is None:
        raise ValueError(f"argv contains no probe token: {argv!r}")
    sentinel = sentinel_path(token)
    sentinel.unlink(missing_ok=True)
    try:
        subprocess.run(
            argv,
            timeout=PROBE_TIMEOUT_S,
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        pass
    except FileNotFoundError:
        return False
    # Hook may have written the sentinel before the host CLI bailed; poll
    # briefly for very fast hooks where subprocess.run returned before
    # the OS flushed.
    for _ in range(5):
        if sentinel.exists():
            sentinel.unlink(missing_ok=True)
            return True
        time.sleep(0.1)
    return False
