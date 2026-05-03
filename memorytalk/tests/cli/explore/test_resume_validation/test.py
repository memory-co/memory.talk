"""resume rejects sessions that aren't under the explore project dir."""
from __future__ import annotations

from memorytalk.tests.cli.explore.conftest import make_round, write_jsonl


def test_resume_unknown_uuid_rejects(explore_env):
    result = explore_env.runner.invoke(explore_env.main, [
        "explore", "resume", "nope-uuid",
        "--data-root", str(explore_env.data_root),
    ])
    # Click BadParameter → exit 2, message references the UUID
    assert result.exit_code == 2
    assert "not in the explore namespace" in result.output


def test_resume_known_uuid_attempts_exec(explore_env, monkeypatch):
    """When the uuid IS valid, resume reaches os.execvp.

    We stub both ``os.chdir`` and ``os.execvp`` so the test process's
    working directory and identity stay intact (otherwise subsequent
    tests inherit a broken cwd).
    """
    import os as _os
    write_jsonl(explore_env.project_dir / "valid.jsonl", [
        make_round("2026-05-03T10:00:00Z"),
    ])

    captured: dict = {}

    def fake_chdir(d):
        captured["cwd"] = str(d)

    def fake_execvp(file, args):
        captured["file"] = file
        captured["args"] = list(args)
        raise SystemExit(99)

    monkeypatch.setattr("memorytalk.cli.explore.os.chdir", fake_chdir)
    monkeypatch.setattr("memorytalk.cli.explore.os.execvp", fake_execvp)

    result = explore_env.runner.invoke(explore_env.main, [
        "explore", "resume", "valid",
        "--data-root", str(explore_env.data_root),
    ])
    assert result.exit_code == 99
    assert captured["file"] == "claude"
    assert captured["args"] == ["claude", "--resume", "valid"]
    assert captured["cwd"] == str(explore_env.explore_cwd)
