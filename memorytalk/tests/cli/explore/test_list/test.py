"""explore list — reads ~/.claude/projects/<derived>/*.jsonl directly."""
from __future__ import annotations
import json

from memorytalk.tests.cli.explore.conftest import make_round, write_jsonl


def _run_list(env, *args) -> tuple[int, dict]:
    result = env.runner.invoke(env.main, [
        "explore", "list", *args,
        "--data-root", str(env.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


def test_list_empty_when_no_sessions(explore_env):
    code, out = _run_list(explore_env)
    assert code == 0, out
    assert out["records"] == []
    assert str(explore_env.explore_cwd) == out["explore_cwd"]


def test_list_one_session_with_card_create(explore_env):
    write_jsonl(explore_env.project_dir / "abc-123.jsonl", [
        make_round("2026-05-03T10:00:00Z", text="hello"),
        make_round("2026-05-03T10:01:00Z", role="assistant",
                   tool_use_command="memory-talk card create '{\"summary\": \"x\"}'"),
        make_round("2026-05-03T10:02:00Z", text="ok"),
    ])
    code, out = _run_list(explore_env)
    assert code == 0
    assert len(out["records"]) == 1
    r = out["records"][0]
    assert r["session_id"] == "sess_abc-123"
    assert r["session_uuid"] == "abc-123"
    assert r["rounds"] == 3
    assert r["cards"] == 1


def test_list_sorts_newest_first(explore_env):
    write_jsonl(explore_env.project_dir / "old.jsonl", [
        make_round("2026-04-01T00:00:00Z"),
    ])
    write_jsonl(explore_env.project_dir / "new.jsonl", [
        make_round("2026-05-01T00:00:00Z"),
    ])
    write_jsonl(explore_env.project_dir / "mid.jsonl", [
        make_round("2026-04-15T00:00:00Z"),
    ])
    code, out = _run_list(explore_env)
    assert code == 0
    assert [r["session_uuid"] for r in out["records"]] == ["new", "mid", "old"]


def test_list_limit(explore_env):
    for ts, name in [
        ("2026-04-01T00:00:00Z", "a"),
        ("2026-05-01T00:00:00Z", "b"),
        ("2026-04-15T00:00:00Z", "c"),
    ]:
        write_jsonl(explore_env.project_dir / f"{name}.jsonl", [make_round(ts)])
    code, out = _run_list(explore_env, "--limit", "2")
    assert code == 0
    assert len(out["records"]) == 2


def test_list_skips_empty_jsonl(explore_env):
    (explore_env.project_dir / "empty.jsonl").write_text("")
    write_jsonl(explore_env.project_dir / "real.jsonl", [
        make_round("2026-05-03T10:00:00Z"),
    ])
    code, out = _run_list(explore_env)
    assert code == 0
    assert len(out["records"]) == 1
    assert out["records"][0]["session_uuid"] == "real"


def test_list_handles_missing_project_dir(tmp_path, monkeypatch):
    """If no claude project dir exists yet, list returns empty cleanly."""
    from click.testing import CliRunner
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    data_root = tmp_path / ".memory-talk"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        '{"embedding": {"provider": "dummy", "dim": 384}}'
    )
    # No explore.cwd dir → no claude project dir → empty list
    runner = CliRunner()
    from memorytalk.cli import main
    result = runner.invoke(main, [
        "explore", "list", "--data-root", str(data_root), "--json",
    ])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["records"] == []
