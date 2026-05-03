"""explore detail — view one exploration record."""
from __future__ import annotations
import json

from memorytalk.tests.cli.explore.conftest import make_round, write_jsonl


def _run_detail(env, sid, *args) -> tuple[int, str]:
    result = env.runner.invoke(env.main, [
        "explore", "detail", sid, *args,
        "--data-root", str(env.data_root),
    ])
    # Markdown errors go to stderr; JSON errors go to stdout. Combine
    # both for the convenience of error-path assertions.
    return result.exit_code, (result.stdout or "") + (result.stderr or "")


def _run_detail_json(env, sid):
    code, out = _run_detail(env, sid, "--json")
    return code, json.loads(out) if code == 0 else out


def test_detail_existing_session(explore_env):
    write_jsonl(explore_env.project_dir / "abc-123.jsonl", [
        make_round("2026-05-03T10:00:00Z"),
        make_round("2026-05-03T10:01:00Z", role="assistant",
                   tool_use_command="memory-talk card create '{}'"),
        make_round("2026-05-03T10:02:00Z", role="assistant",
                   tool_use_command="memory-talk card create '{}'"),
    ])
    code, out = _run_detail_json(explore_env, "sess_abc-123")
    assert code == 0
    assert out["session_id"] == "sess_abc-123"
    assert out["rounds"] == 3
    assert out["cards"] == 2


def test_detail_accepts_raw_uuid(explore_env):
    write_jsonl(explore_env.project_dir / "raw.jsonl", [
        make_round("2026-05-03T10:00:00Z"),
    ])
    code, out = _run_detail_json(explore_env, "raw")
    assert code == 0
    assert out["session_uuid"] == "raw"


def test_detail_missing_session_errors(explore_env):
    code, out = _run_detail(explore_env, "sess_nope")
    assert code == 1
    assert "not found in explore namespace" in out
