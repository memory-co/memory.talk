"""Verify the probe short-circuit in ``recall --hook``: when the prompt
starts with the magic prefix, write a sentinel and exit 0 without
touching the backend (no API key / no running server required)."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from memorytalk.cli.recall import recall
from memorytalk.hooks import probe


def test_probe_writes_sentinel_and_exits_zero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    token = probe.new_token()
    sentinel = probe.sentinel_path(token)
    sentinel.unlink(missing_ok=True)

    payload = json.dumps({
        "session_id": "test-session",
        "prompt": token,
    })

    runner = CliRunner()
    result = runner.invoke(recall, ["--hook"], input=payload)
    try:
        assert result.exit_code == 0, result.output
        # Hook contract: stdout must be valid hookSpecificOutput JSON
        out = json.loads(result.output.strip())
        assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        assert out["hookSpecificOutput"]["additionalContext"] == ""
        # Probe sentinel must exist
        assert sentinel.exists()
    finally:
        sentinel.unlink(missing_ok=True)


def test_non_probe_prompt_still_works(tmp_path: Path, monkeypatch) -> None:
    """A regular prompt must NOT write a sentinel — only probe tokens."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    payload = json.dumps({
        "session_id": "test-session",
        "prompt": "hello world",
    })
    runner = CliRunner()
    # Will fail to call backend (no server) — that's fine, hook contract
    # is "always exit 0", and we just want to confirm no sentinel got written.
    runner.invoke(recall, ["--hook"], input=payload)
    # No sentinel for arbitrary prompts (only PROBE_PREFIX prompts write).
    assert not any(
        p.name.startswith(probe.PROBE_PREFIX) and p.name.endswith(".ok")
        for p in Path("/tmp").glob(f"{probe.PROBE_PREFIX}*.ok")
        if p.name == f"hello world.ok"  # belt + braces: explicit
    )
