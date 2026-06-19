"""``memory.talk recall hook --source X`` — host plugin integration.

Contract: the hook MUST emit a valid ``hookSpecificOutput`` JSON to
stdout and exit 0 in every branch — a non-zero exit blocks the user's
prompt in the host CLI.

0.9.0: ``--source`` is required; the old ``--hook`` flag is gone.
"""
from __future__ import annotations
import json

from click.testing import CliRunner


def _parse_hook_output(stdout: str) -> dict:
    """The hook writes one JSON object followed by a newline."""
    return json.loads(stdout.strip())


def _expected_shape(ctx: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }


def _runner() -> CliRunner:
    return CliRunner()


def test_hook_recalls_and_emits_json(tmp_path, monkeypatch):
    """Happy path: stdin payload → POST /v4/recall → wrap response in
    hookSpecificOutput."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))

    from memorytalk.cli import recall as recall_mod
    from memorytalk.adapters import get_adapter
    captured = {}

    def _fake_api(method, path, cfg, json_body=None, timeout=30.0, params=None):
        assert method == "POST" and path == "/v4/recall"
        captured["body"] = json_body
        return {
            "session_id": json_body["session_id"],
            "prompt": "what was that bug?",
            "cards": [{
                "card_id": "card_001", "issue": "which keepalive?",
                "relevance": 1.0,
                "answer": {"claim": "tcp keepalive issue", "scope": None,
                           "credence": 1, "up_count": 1, "down_count": 0,
                           "neutral_count": 0, "position_id": "pos_1"},
                "alternatives": [],
            }],
        }
    monkeypatch.setattr(recall_mod, "api", _fake_api)

    payload = json.dumps({"session_id": "sess_abc", "prompt": "what was that bug?"})
    runner = _runner()
    result = runner.invoke(
        recall_mod.recall, ["hook", "--source", "claude-code"],
        input=payload,
    )
    assert result.exit_code == 0, result.output

    body = _parse_hook_output(result.stdout)
    assert body["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert "card_001" in ctx
    assert "tcp keepalive issue" in ctx

    # The CLI mints the canonical session_id client-side; body carries the
    # canonical id + prompt (no source — that's only used for minting).
    canonical = get_adapter("claude-code").mint_session_id("sess_abc")
    assert captured["body"]["session_id"] == canonical
    assert captured["body"]["prompt"] == "what was that bug?"


def test_hook_mints_canonical_session_id(tmp_path, monkeypatch):
    """The CLI mints the canonical session_id from --source before POSTing
    to /v4/recall (the card recall takes a canonical id, not source)."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))

    from memorytalk.cli import recall as recall_mod
    from memorytalk.adapters import get_adapter
    captured = {}

    def _fake_api(method, path, cfg, json_body=None, timeout=30.0, params=None):
        captured["path"] = path
        captured["body"] = json_body
        return {"session_id": json_body["session_id"], "prompt": "p", "cards": []}
    monkeypatch.setattr(recall_mod, "api", _fake_api)

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall,
        ["hook", "--source", "codex"],
        input=json.dumps({"session_id": "s", "prompt": "p"}),
    )
    assert result.exit_code == 0, result.output
    assert captured["path"] == "/v4/recall"
    assert captured["body"]["session_id"] == get_adapter("codex").mint_session_id("s")


def test_hook_empty_recall_emits_empty_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))
    from memorytalk.cli import recall as recall_mod
    monkeypatch.setattr(recall_mod, "api", lambda *a, **k: {
        "session_id": "s", "prompt": "q", "cards": [],
    })

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall, ["hook", "--source", "claude-code"],
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

    from memorytalk.cli import recall as recall_mod
    runner = _runner()

    # Two categories:
    #   - missing key / wrong type → stdin parses as JSON but the hook
    #     handler can't extract session_id/prompt → empty context
    #   - "not json at all" → _read_stdin_payload returns None →
    #     positional-mode path runs → exits with "needs SESSION_ID..."
    #     error (exit 2). That's not a hook failure — it's the user
    #     misusing positional mode without args. We test the JSON
    #     parse failures here.
    for bad_input in [
        json.dumps({"session_id": "s"}),                          # missing prompt
        json.dumps({"prompt": "p"}),                              # missing session_id
        json.dumps({"session_id": 123, "prompt": "p"}),           # wrong type
    ]:
        result = runner.invoke(
            recall_mod.recall, ["hook", "--source", "claude-code"],
            input=bad_input,
        )
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

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall, ["hook", "--source", "claude-code"],
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
        return {"session_id": "s", "prompt": "p", "cards": []}
    monkeypatch.setattr(recall_mod, "api", _track)

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall, ["hook", "--source", "claude-code"],
        input=json.dumps({
            "session_id": "s", "prompt": "p", "cwd": str(explore_dir),
        }),
    )
    assert result.exit_code == 0
    assert called["n"] == 0, "API should not be called in explore cwd"
    assert _parse_hook_output(result.stdout) == _expected_shape("")


def test_hook_does_not_suppress_outside_explore_cwd(tmp_path, monkeypatch):
    """Sanity check: any cwd that ISN'T explore.cwd falls through to
    normal recall."""
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
        return {"session_id": "s", "prompt": "p", "cards": []}
    monkeypatch.setattr(recall_mod, "api", _track)

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall, ["hook", "--source", "claude-code"],
        input=json.dumps({
            "session_id": "s", "prompt": "p", "cwd": str(other_dir),
        }),
    )
    assert result.exit_code == 0
    assert called["n"] == 1, "API should be called when cwd != explore.cwd"


def test_recall_hook_requires_source():
    """Click rejects ``recall hook`` without ``--source`` — 0.9.0
    contract. The whole point of dropping legacy ``prefix_session_id``
    was to make this impossible to forget."""
    from memorytalk.cli.recall import recall
    runner = _runner()
    result = runner.invoke(recall, ["hook"])
    assert result.exit_code == 2
    # Click puts the missing-option message in stderr.
    assert "source" in (result.stderr or result.output).lower()


def test_recall_hook_positional_mode_without_stdin(tmp_path, monkeypatch):
    """Manual / debug use: pass positional args, no stdin."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))

    from memorytalk.cli import recall as recall_mod
    monkeypatch.setattr(recall_mod, "api", lambda *a, **k: {
        "session_id": "sess-x", "prompt": "q",
        "cards": [{
            "card_id": "card_1", "issue": "the issue", "relevance": 1.0,
            "answer": {"claim": "the answer", "scope": None, "credence": 1,
                       "up_count": 1, "down_count": 0, "neutral_count": 0,
                       "position_id": "pos_1"},
            "alternatives": [],
        }],
    })

    runner = _runner()
    result = runner.invoke(
        recall_mod.recall,
        ["hook", "--source", "claude-code", "test-session", "what about it"],
    )
    assert result.exit_code == 0, result.output
    assert "card_1" in result.output
    assert "the answer" in result.output
