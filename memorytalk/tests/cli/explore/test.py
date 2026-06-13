"""explore — CLI surface + request wiring. See README.md."""
from __future__ import annotations

from click.testing import CliRunner


def test_explore_group_lists_subcommands():
    from memorytalk.cli import main
    r = CliRunner().invoke(main, ["explore", "--help"])
    assert r.exit_code == 0
    for sub in ("create", "view", "list"):
        assert sub in r.output


def test_explore_create_posts_entrypoint(monkeypatch):
    calls = []

    def _fake_api(method, path, cfg, json_body=None, timeout=30.0, params=None):
        calls.append((method, path, json_body))
        return {
            "explore_id": "explore_X", "divider_at": "2026-05-15T00:00:00Z",
            "dir_path": "/d", "prior_count": 2, "posterior_count": 1,
        }

    import memorytalk.cli.explore as ex
    monkeypatch.setattr(ex, "api", _fake_api)
    from memorytalk.cli import main

    r = CliRunner().invoke(main, ["explore", "create", "sess-x", "--json"])

    assert r.exit_code == 0, r.output
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/v3/explores"
    assert calls[0][2]["entrypoint_session_id"] == "sess-x"
