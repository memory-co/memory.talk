"""`memory-talk recall --hook` — Claude Code UserPromptSubmit integration.

Contract: the hook MUST emit a valid ``hookSpecificOutput`` JSON to
stdout and exit 0 in every branch — a non-zero exit blocks the user's
prompt in Claude Code.
"""
from __future__ import annotations
import json
import pathlib

import pytest
from click.testing import CliRunner


def _parse_hook_output(stdout: str) -> dict:
    """The hook writes one JSON object followed by a newline."""
    return json.loads(stdout.strip())


def _runner() -> CliRunner:
    """We split stdout and stderr in assertions: the hook writes the
    JSON envelope to stdout and any diagnostic warning to stderr. (As of
    click 8.x, ``result.stdout`` and ``result.stderr`` are already
    separated by default.)"""
    return CliRunner()


def _expected_shape(ctx: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }


def test_hook_recalls_and_emits_json(tmp_path, monkeypatch):
    """Happy path: stdin payload → POST /v3/recall → wrap response in
    hookSpecificOutput."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))

    # Stub the HTTP layer so the test doesn't need a live server.
    from memorytalk.cli import recall as recall_mod
    def _fake_api(method, path, cfg, json_body=None, timeout=30.0, params=None):
        assert method == "POST" and path == "/v3/recall"
        assert json_body == {"session_id": "sess_abc", "prompt": "what was that bug?"}
        return {
            "session_id": "sess_abc", "query": "what was that bug?",
            "recalled": [{"card_id": "card_001", "insight": "tcp keepalive issue"}],
            "skipped_already_recalled": [],
        }
    monkeypatch.setattr(recall_mod, "api", _fake_api)

    payload = json.dumps({"session_id": "sess_abc", "prompt": "what was that bug?"})
    from memorytalk.cli.recall import recall
    runner = _runner()
    result = runner.invoke(recall, ["--hook"], input=payload)
    assert result.exit_code == 0, result.output

    body = _parse_hook_output(result.stdout)
    assert body["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert "memory-talk read card_001" in ctx
    assert "tcp keepalive issue" in ctx


def test_hook_empty_recall_emits_empty_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))
    from memorytalk.cli import recall as recall_mod
    monkeypatch.setattr(recall_mod, "api", lambda *a, **k: {
        "session_id": "s", "query": "q", "recalled": [], "skipped_already_recalled": [],
    })

    from memorytalk.cli.recall import recall
    runner = _runner()
    result = runner.invoke(
        recall, ["--hook"],
        input=json.dumps({"session_id": "s", "prompt": "q"}),
    )
    assert result.exit_code == 0
    assert _parse_hook_output(result.stdout) == _expected_shape("")


def test_hook_malformed_stdin_returns_empty_context(tmp_path, monkeypatch):
    """Bad JSON, missing keys, wrong types — all must exit 0 with empty
    context. We must never block the user prompt over a parse error."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))

    from memorytalk.cli.recall import recall
    runner = _runner()

    for bad_input in [
        "not json at all",
        json.dumps({"session_id": "s"}),                          # missing prompt
        json.dumps({"prompt": "p"}),                              # missing session_id
        json.dumps({"session_id": 123, "prompt": "p"}),           # wrong type
    ]:
        result = runner.invoke(recall, ["--hook"], input=bad_input)
        assert result.exit_code == 0, f"input={bad_input!r}: {result.output}"
        assert _parse_hook_output(result.stdout) == _expected_shape(""), bad_input


def test_hook_api_failure_returns_empty_context(tmp_path, monkeypatch):
    """Server unreachable / 5xx / timeout → empty context, exit 0."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))
    from memorytalk.cli import recall as recall_mod
    def _explode(*a, **k):
        raise ConnectionError("server is down")
    monkeypatch.setattr(recall_mod, "api", _explode)

    from memorytalk.cli.recall import recall
    runner = _runner()
    result = runner.invoke(
        recall, ["--hook"],
        input=json.dumps({"session_id": "s", "prompt": "p"}),
    )
    assert result.exit_code == 0
    assert _parse_hook_output(result.stdout) == _expected_shape("")


def test_hook_suppresses_recall_in_explore_cwd(tmp_path, monkeypatch):
    """When the caller's cwd matches settings.explore.cwd, the hook
    returns empty context WITHOUT calling the API."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    explore_dir = tmp_path / "explore-workspace"
    explore_dir.mkdir()
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
        "explore": {"cwd": str(explore_dir)},
    }))

    called = {"n": 0}
    from memorytalk.cli import recall as recall_mod
    def _track(*a, **k):
        called["n"] += 1
        return {"recalled": []}
    monkeypatch.setattr(recall_mod, "api", _track)

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall, ["--hook"],
        input=json.dumps({
            "session_id": "s", "prompt": "p", "cwd": str(explore_dir),
        }),
    )
    assert result.exit_code == 0
    assert called["n"] == 0, "API should not be called in explore cwd"
    assert _parse_hook_output(result.stdout) == _expected_shape("")


def test_hook_does_not_suppress_outside_explore_cwd(tmp_path, monkeypatch):
    """Sanity check: any cwd that ISN'T explore.cwd should fall through
    to the normal recall path."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    explore_dir = tmp_path / "explore-workspace"
    explore_dir.mkdir()
    other_dir = tmp_path / "regular-project"
    other_dir.mkdir()
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
        "explore": {"cwd": str(explore_dir)},
    }))

    called = {"n": 0}
    from memorytalk.cli import recall as recall_mod
    def _track(*a, **k):
        called["n"] += 1
        return {"recalled": []}
    monkeypatch.setattr(recall_mod, "api", _track)

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall, ["--hook"],
        input=json.dumps({
            "session_id": "s", "prompt": "p", "cwd": str(other_dir),
        }),
    )
    assert result.exit_code == 0
    assert called["n"] == 1, "API should be called when cwd != explore.cwd"


def test_non_hook_mode_still_requires_args():
    """Regression: making session_id/prompt optional for --hook must
    not weaken the validation in the normal CLI path."""
    from memorytalk.cli.recall import recall
    runner = _runner()
    result = runner.invoke(recall, [])
    assert result.exit_code == 2
    assert "requires SESSION_ID and PROMPT" in result.stderr
